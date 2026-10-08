"""Local reviewed Work Intake; export is a dry run with no external transport."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from edn.operations.intake_security import (
    AnchoredDirectory,
    require_supported_platform,
    verify_evidence,
)

SERVICES = (
    "Network infrastructure",
    "Field engineering",
    "Site assessment",
    "Fault response",
    "Other / not sure",
)
URGENCY_LEVELS = ("Routine", "Time-sensitive", "Urgent")
LIMITS = {
    "contactName": 100,
    "company": 120,
    "email": 254,
    "phone": 30,
    "siteLocation": 240,
    "preferredDate": 10,
    "jobDescription": 4000,
    "reference": 100,
}
INPUT_FIELDS = frozenset((*LIMITS, "serviceRequired", "urgency"))
FIELDS = INPUT_FIELDS
FIELD_MAPPING = {
    "contactName": "ContactName",
    "company": "Company",
    "email": "Email",
    "phone": "Phone",
    "siteLocation": "Site_x002f_Location",
    "serviceRequired": "ServiceRequired",
    "preferredDate": "PreferredDate",
    "urgency": "Urgency",
    "jobDescription": "JobDescription",
    "reference": "CustomerReference",
}


class IntakeError(ValueError):
    """Fixed diagnostic; no request content belongs in public errors."""


class IntakeCommitUncertainError(IntakeError):
    """Publication occurred but its directory durability could not be confirmed."""


def validate_fields(fields: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(fields, Mapping) or set(fields) - INPUT_FIELDS:
        raise IntakeError("Unsupported request fields")
    result: dict[str, str] = {}
    for name in INPUT_FIELDS:
        value = fields.get(name, "")
        if not isinstance(value, str):
            raise IntakeError("Request fields must be text")
        value = value.strip()
        if any(
            unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"}
            and not (name == "jobDescription" and c in "\n\r")
            for c in value
        ):
            raise IntakeError("Request contains unsupported controls")
        try:
            length = len(value.encode("utf-16-le")) // 2
        except UnicodeEncodeError:
            raise IntakeError("Request field contains invalid Unicode") from None
        if length > LIMITS.get(name, 100):
            raise IntakeError("Request field exceeds its limit")
        result[name] = value
    if any(
        not result[name]
        for name in (
            "contactName",
            "email",
            "phone",
            "siteLocation",
            "jobDescription",
        )
    ):
        raise IntakeError("Required request fields are missing")
    result["email"] = result["email"].lower()
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result["email"]) is None:
        raise IntakeError("Invalid email address")
    phone = result["phone"]
    if (
        re.fullmatch(r"[+0-9][0-9\s().-]*", phone) is None
        or len(re.sub(r"[^0-9]", "", phone)) < 8
    ):
        raise IntakeError("Invalid phone number")
    result["phone"] = ("+" if phone.startswith("+") else "") + re.sub(
        r"[^0-9]", "", phone
    )
    if (
        result["serviceRequired"] not in SERVICES
        or result["urgency"] not in URGENCY_LEVELS
    ):
        raise IntakeError("Invalid service or urgency")
    if result["preferredDate"]:
        try:
            if (
                re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", result["preferredDate"])
                is None
            ):
                raise ValueError
            date.fromisoformat(result["preferredDate"])
        except ValueError:
            raise IntakeError("Invalid preferred date") from None
    return result


def _attachments(
    values: Sequence[Mapping[str, object]], request_id: str
) -> tuple[dict[str, object], ...]:
    result = []
    total_size = 0
    allowed = {
        "attachment_id",
        "request_id",
        "original_name",
        "media_type",
        "size_bytes",
        "sha256",
    }
    for value in values:
        if not isinstance(value, Mapping) or set(value) != allowed:
            raise IntakeError("Invalid attachment metadata")
        item = dict(value)
        if item["request_id"] != request_id:
            raise IntakeError("Attachment belongs to another request")
        _identity(item["attachment_id"])
        if (
            not isinstance(item["original_name"], str)
            or not item["original_name"]
            or not isinstance(item["media_type"], str)
            or type(item["size_bytes"]) is not int
            or not 0 < item["size_bytes"] <= 20_000_000
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
        ):
            raise IntakeError("Invalid attachment metadata")
        result.append(item)
        size = item["size_bytes"]
        assert isinstance(size, int)
        total_size += size
    if (
        total_size > 100_000_000
        or len(result) > 100
        or len({item["attachment_id"] for item in result}) != len(result)
    ):
        raise IntakeError("Attachment count or identity is invalid")
    return tuple(result)


def _identity(value: object) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise IntakeError("Invalid request identity") from None
    return value


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(fields: object, attachments: object) -> str:
    return hashlib.sha256(_json([fields, attachments]).encode()).hexdigest()


def _audit_row(
    connection: sqlite3.Connection, request_id: str, row: tuple[object, ...]
) -> dict[str, object]:
    try:
        decision_id, revision, content_hash, actor, decided_at, decision, reason = row
        _identity(decision_id)
        if (
            type(revision) is not int
            or revision < 1
            or not isinstance(content_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None
            or not isinstance(actor, str)
            or re.fullmatch(
                r"local operator(?: \(self-approval\))?, uid=(0|[1-9][0-9]*)", actor
            )
            is None
            or not isinstance(decided_at, str)
            or decision
            not in {
                "created",
                "approved",
                "edited",
                "edited_approval_invalidated",
                "rejected",
                "cancelled",
                "reopened",
            }
        ):
            raise ValueError
        if decision in {"rejected", "cancelled", "reopened"}:
            if (
                not isinstance(reason, str)
                or not reason.strip()
                or len(reason) > 500
                or any(
                    unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in reason
                )
            ):
                raise ValueError
        elif reason is not None:
            raise ValueError
        timestamp = datetime.fromisoformat(decided_at)
        if timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise ValueError
        revision_row = connection.execute(
            "SELECT fields,attachments FROM intake_revisions "
            "WHERE request_id=? AND revision=?",
            (request_id, revision),
        ).fetchone()
        if revision_row is None:
            raise ValueError
        fields = validate_fields(json.loads(revision_row[0]))
        attached = _attachments(json.loads(revision_row[1]), request_id)
        if _digest(fields, attached) != content_hash:
            raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise IntakeError("Stored approval audit is invalid") from None
    return dict(
        zip(
            ("revision", "content_hash", "actor", "decided_at", "decision", "reason"),
            (revision, content_hash, actor, decided_at, decision, reason),
            strict=True,
        )
    )


@dataclass(frozen=True)
class IntakeRequest:
    request_id: str
    revision: int
    fields: dict[str, str]
    attachments: tuple[dict[str, object], ...]
    state: str
    sync_status: str
    created_at: str
    updated_at: str
    approved_revision: int | None
    approval_actor: str | None = None
    approval_timestamp: str | None = None
    entered_by: str | None = None


DDL = """CREATE TABLE intake_requests (
request_id TEXT PRIMARY KEY NOT NULL,
revision INTEGER NOT NULL,
state TEXT NOT NULL CHECK(state IN ('draft','approved','rejected','cancelled')),
sync_status TEXT NOT NULL CHECK(sync_status IN ('not_synced','dry_run')),
created_at TEXT NOT NULL,
updated_at TEXT NOT NULL,
approved_revision INTEGER,
approval_hash TEXT,
schema_version INTEGER NOT NULL CHECK(schema_version=1)
)"""
REVISIONS_DDL = """CREATE TABLE intake_revisions (
request_id TEXT NOT NULL REFERENCES intake_requests(request_id),
revision INTEGER NOT NULL,
fields TEXT NOT NULL,
attachments TEXT NOT NULL,
PRIMARY KEY(request_id,revision)
)"""
APPROVALS_DDL = """CREATE TABLE intake_approvals (
decision_id TEXT PRIMARY KEY NOT NULL,
request_id TEXT NOT NULL REFERENCES intake_requests(request_id),
revision INTEGER NOT NULL,
content_hash TEXT NOT NULL,
actor TEXT NOT NULL,
decided_at TEXT NOT NULL,
decision TEXT NOT NULL
CHECK(decision IN ('created','approved','edited',
'edited_approval_invalidated','rejected','cancelled','reopened')),
reason TEXT
)"""


@dataclass(frozen=True)
class IntakeListResult:
    requests: tuple[IntakeRequest, ...]
    malformed: int


@dataclass(frozen=True)
class SubmissionIntent:
    submission_id: str
    fields: dict[str, str] | None
    request_id: str | None


SUBMISSIONS_DDL = """CREATE TABLE intake_submissions (
submission_id TEXT PRIMARY KEY NOT NULL,
fields TEXT,
attachments TEXT,
initial_hash TEXT,
request_id TEXT UNIQUE REFERENCES intake_requests(request_id)
)"""
INTENT_DDL = """CREATE TABLE intake_intent (
singleton INTEGER PRIMARY KEY CHECK(singleton=1),
submission_id TEXT NOT NULL REFERENCES intake_submissions(submission_id)
)"""


MAX_DATABASE_BYTES = 100_000_000


class _ProtectedConnection(sqlite3.Connection):
    anchor: AnchoredDirectory
    storage_lock: AbstractContextManager[None]
    database_name: str
    original_inode: tuple[int, int] | None
    read_only_snapshot: bool
    initialise_snapshot: bool
    released: bool = False

    def _persist(self) -> None:
        payload = self.serialize()
        if len(payload) > MAX_DATABASE_BYTES:
            raise IntakeError("Request metadata database exceeds its size bound")
        pending = self.database_name + ".pending-" + str(uuid4())
        try:
            descriptor = self.anchor.open_file(pending, create=True, write=True)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.original_inode is None:
                self.anchor.publish(pending, self.database_name)
            else:
                descriptor = self.anchor.open_file(self.database_name)
                try:
                    observed = os.fstat(descriptor)
                    if (observed.st_dev, observed.st_ino) != self.original_inode:
                        raise IntakeError("Request store changed during transaction")
                finally:
                    os.close(descriptor)
                self.anchor.replace(pending, self.database_name)
            try:
                os.fsync(self.anchor.fd)
            except OSError:
                raise IntakeCommitUncertainError(
                    "Request publication is unconfirmed; reload before retrying"
                ) from None
        finally:
            if self.anchor.exists(pending):
                self.anchor.unlink(pending)

    def close(self) -> None:
        try:
            super().close()
        finally:
            if not self.released:
                self.released = True
                self.storage_lock.__exit__(None, None, None)
                self.anchor.close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            result = super().__exit__(exc_type, exc_value, traceback)
            if (
                exc_type is None
                and not self.read_only_snapshot
                and (self.total_changes > 0 or self.initialise_snapshot)
            ):
                self._persist()
            return result
        finally:
            self.close()


class IntakeStore:
    def __init__(
        self, path: Path, *, read_only: bool = False, evidence_root: Path | None = None
    ) -> None:
        self.path = path
        self.read_only = read_only
        self.evidence_root = evidence_root

    def _write(self) -> None:
        if self.read_only:
            raise IntakeError("Read-only request store cannot write")

    @staticmethod
    def _validate(connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        expected = sorted(
            [("intake_requests", DDL), ("intake_revisions", REVISIONS_DDL)]
        )
        expected = sorted([*expected, ("intake_approvals", APPROVALS_DDL)])
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 2:
            expected = sorted(
                [
                    *expected,
                    ("intake_submissions", SUBMISSIONS_DDL),
                    ("intake_intent", INTENT_DDL),
                ]
            )
        if rows != expected or version not in {1, 2}:
            raise IntakeError("Unsupported request store schema")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise IntakeError("Request store integrity is invalid")

    def _connect(self, *, initialise: bool = False) -> sqlite3.Connection:
        require_supported_platform()
        if not hasattr(sqlite3.Connection, "serialize") or not hasattr(
            sqlite3.Connection, "deserialize"
        ):
            raise IntakeError("Protected SQLite snapshots are unavailable")
        directory = AnchoredDirectory(self.path.parent)
        if not initialise and not directory.exists(self.path.name):
            directory.close()
            raise sqlite3.OperationalError("Request store is unavailable")
        storage_lock = directory.lock(self.path.name + ".lock")
        try:
            storage_lock.__enter__()
            payload = None
            original_inode = None
            try:
                descriptor = directory.open_file(self.path.name)
            except FileNotFoundError:
                if not initialise:
                    raise sqlite3.OperationalError(
                        "Request store is unavailable"
                    ) from None
            else:
                with os.fdopen(descriptor, "rb") as stream:
                    observed = os.fstat(stream.fileno())
                    original_inode = (observed.st_dev, observed.st_ino)
                    payload = stream.read(MAX_DATABASE_BYTES + 1)
                if len(payload) > MAX_DATABASE_BYTES:
                    raise IntakeError(
                        "Request metadata database exceeds its size bound"
                    )
            if any(
                directory.exists(self.path.name + suffix)
                for suffix in ("-journal", "-wal", "-shm")
            ):
                raise IntakeError("Active SQLite sidecars require owner-led recovery")
            connection = sqlite3.connect(":memory:", factory=_ProtectedConnection)
            connection.anchor = directory
            connection.storage_lock = storage_lock
            connection.database_name = self.path.name
            connection.original_inode = original_inode
            connection.read_only_snapshot = self.read_only
            connection.initialise_snapshot = initialise and payload is None
            if payload is not None:
                connection.deserialize(payload)
            connection.execute("PRAGMA foreign_keys=ON")
            if not connection.initialise_snapshot:
                self._validate(connection)
            if self.read_only:
                connection.execute("PRAGMA query_only=ON")
        except BaseException:
            if "connection" in locals():
                connection.close()
            else:
                storage_lock.__exit__(None, None, None)
                directory.close()
            raise
        return connection

    def initialise(self) -> None:
        require_supported_platform()
        self._write()
        with self._connect(initialise=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 2:
                return
            connection.execute("BEGIN IMMEDIATE")
            if version == 0:
                connection.execute(DDL)
                connection.execute(REVISIONS_DDL)
                connection.execute(APPROVALS_DDL)
            connection.execute(SUBMISSIONS_DDL)
            connection.execute(INTENT_DDL)
            if version == 1:
                for (request_id,) in connection.execute(
                    "SELECT request_id FROM intake_requests"
                ).fetchall():
                    self._get(connection, request_id)
                    original = connection.execute(
                        "SELECT fields,attachments FROM intake_revisions "
                        "WHERE request_id=? AND revision=1",
                        (request_id,),
                    ).fetchone()
                    if original is None:
                        raise IntakeError("Original request revision is missing")
                    original_fields = validate_fields(json.loads(original[0]))
                    original_evidence = _attachments(
                        json.loads(original[1]), request_id
                    )
                    key = str(uuid5(NAMESPACE_URL, "edn-intake-manual:" + request_id))
                    connection.execute(
                        "INSERT INTO intake_submissions VALUES (?,?,?,?,?)",
                        (
                            key,
                            _json(original_fields),
                            _json(original_evidence),
                            _digest(original_fields, original_evidence),
                            request_id,
                        ),
                    )
            connection.execute("PRAGMA user_version=2")
            assert isinstance(connection, _ProtectedConnection)
            connection.initialise_snapshot = True

    @staticmethod
    def _submission_schema(connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone() != (2,):
            raise IntakeError("Initialize submission receipts explicitly")

    def begin_submission(self) -> SubmissionIntent:
        self._write()
        submission_id = str(uuid4())
        with self._connect() as connection:
            self._submission_schema(connection)
            connection.execute(
                "INSERT INTO intake_submissions VALUES (?,NULL,NULL,NULL,NULL)",
                (submission_id,),
            )
            connection.execute(
                "INSERT INTO intake_intent VALUES (1,?) ON CONFLICT(singleton) "
                "DO UPDATE SET submission_id=excluded.submission_id",
                (submission_id,),
            )
        return SubmissionIntent(submission_id, None, None)

    def current_submission(self) -> SubmissionIntent | None:
        with self._connect() as connection:
            self._submission_schema(connection)
            row = connection.execute(
                "SELECT s.submission_id,s.fields,s.request_id,s.attachments,"
                "s.initial_hash FROM "
                "intake_intent i JOIN intake_submissions s ON "
                "s.submission_id=i.submission_id WHERE i.singleton=1"
            ).fetchone()
            if row is None:
                return None
            try:
                _identity(row[0])
                fields = (
                    validate_fields(json.loads(row[1])) if row[1] is not None else None
                )
                if row[2] is not None:
                    self._get(connection, row[2])
                    evidence = _attachments(json.loads(row[3]), row[2])
                    if row[4] != _digest(fields, evidence):
                        raise ValueError
                elif fields is not None or row[3] is not None or row[4] is not None:
                    raise ValueError
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                raise IntakeError("Stored submission intent is invalid") from None
            return SubmissionIntent(row[0], fields, row[2])

    @staticmethod
    def _get(connection: sqlite3.Connection, request_id: str) -> IntakeRequest:
        _identity(request_id)
        row = connection.execute(
            "SELECT q.*,r.fields,r.attachments FROM intake_requests q JOIN "
            "intake_revisions r ON r.request_id=q.request_id AND "
            "r.revision=q.revision WHERE q.request_id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise IntakeError("Request is missing")
        try:
            fields = validate_fields(json.loads(row[9]))
            attachments = _attachments(json.loads(row[10]), request_id)
            if fields != json.loads(row[9]):
                raise ValueError
            if type(row[1]) is not int or row[1] < 1 or row[8] != 1:
                raise ValueError
            for timestamp in (row[4], row[5]):
                if datetime.fromisoformat(timestamp).utcoffset() is None:
                    raise ValueError
            if row[2] not in {"draft", "approved", "rejected", "cancelled"} or row[
                3
            ] not in {
                "not_synced",
                "dry_run",
            }:
                raise ValueError
            if row[2] == "approved":
                if row[6] != row[1] or row[7] != _digest(fields, attachments):
                    raise ValueError
            elif row[6] is not None or row[7] is not None or row[3] != "not_synced":
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise IntakeError("Stored request is invalid") from None
        approval = None
        if row[2] == "approved":
            approval = connection.execute(
                "SELECT "
                "decision_id,revision,content_hash,actor,decided_at,decision,reason "
                ""
                "FROM intake_approvals WHERE request_id=? "
                "AND revision=? AND content_hash=? AND decision='approved' "
                "ORDER BY decided_at DESC,decision_id DESC LIMIT 1",
                (request_id, row[1], row[7]),
            ).fetchone()
            if approval is None:
                raise IntakeError("Approved request audit is missing")
            _audit_row(connection, request_id, approval)
        creation = connection.execute(
            "SELECT decision_id,revision,content_hash,actor,decided_at,decision,reason "
            "FROM intake_approvals WHERE request_id=? AND decision='created' "
            "ORDER BY decided_at,decision_id LIMIT 1",
            (request_id,),
        ).fetchone()
        if creation is None:
            raise IntakeError("Request creation audit is missing")
        _audit_row(connection, request_id, creation)
        if creation[1] != 1 or creation[4] != row[4]:
            raise IntakeError("Request creation timestamp is inconsistent")
        latest = connection.execute(
            "SELECT decision_id,revision,content_hash,actor,decided_at,decision,reason "
            "FROM intake_approvals WHERE request_id=? ORDER BY rowid DESC LIMIT 1",
            (request_id,),
        ).fetchone()
        if latest is None:
            raise IntakeError("Current request audit is missing")
        _audit_row(connection, request_id, latest)
        expected_decisions = {
            "draft": {"created"}
            if row[1] == 1
            else {"edited", "edited_approval_invalidated", "reopened"},
            "approved": {"approved"},
            "rejected": {"rejected"},
            "cancelled": {"cancelled"},
        }
        if (
            latest[1] != row[1]
            or latest[2] != _digest(fields, attachments)
            or latest[5] not in expected_decisions[row[2]]
        ):
            raise IntakeError("Current request state has no matching audited decision")
        return IntakeRequest(
            request_id,
            row[1],
            fields,
            attachments,
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            approval[3] if approval else None,
            approval[4] if approval else None,
            creation[3],
        )

    def get(self, request_id: str) -> IntakeRequest:
        with self._connect() as connection:
            return self._get(connection, request_id)

    def list_requests(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[IntakeRequest, ...]:
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            raise IntakeError("Invalid queue page bounds")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT request_id FROM intake_requests ORDER BY created_at "
                "DESC,request_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return tuple(self._get(connection, row[0]) for row in rows)

    def list_requests_with_diagnostics(
        self, *, limit: int = 50, offset: int = 0
    ) -> IntakeListResult:
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            raise IntakeError("Invalid queue page bounds")
        valid = []
        malformed = 0
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT request_id FROM intake_requests ORDER BY created_at DESC,"
                "request_id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            for row in rows:
                try:
                    valid.append(self._get(connection, row[0]))
                except (IntakeError, ValueError, TypeError, RecursionError):
                    malformed += 1
        return IntakeListResult(tuple(valid), malformed)

    def create(
        self,
        fields: Mapping[str, object],
        *,
        submission_id: str,
        attachments: Sequence[Mapping[str, object]] = (),
    ) -> IntakeRequest:
        self._write()
        _identity(submission_id)
        request_id = str(uuid4())
        cleaned = validate_fields(fields)
        attached = _attachments(attachments, request_id)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            self._submission_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT fields,attachments,initial_hash,request_id FROM "
                "intake_submissions WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
            if receipt is not None and receipt[3] is not None:
                if receipt[:3] != (
                    _json(cleaned),
                    _json(attached),
                    _digest(cleaned, attached),
                ):
                    raise IntakeError(
                        "Submission identity conflicts with original facts"
                    )
                return self._get(connection, receipt[3])
            connection.execute(
                "INSERT INTO intake_requests VALUES "
                "(?,1,'draft','not_synced',?,?,NULL,NULL,1)",
                (request_id, now, now),
            )
            connection.execute(
                "INSERT INTO intake_revisions VALUES (?,1,?,?)",
                (request_id, _json(cleaned), _json(attached)),
            )
            connection.execute(
                "INSERT INTO intake_submissions VALUES (?,?,?,?,?) ON "
                "CONFLICT(submission_id) DO UPDATE SET "
                "fields=excluded.fields,attachments=excluded.attachments,initial_hash=excluded.initial_hash,request_id=excluded.request_id",
                (
                    submission_id,
                    _json(cleaned),
                    _json(attached),
                    _digest(cleaned, attached),
                    request_id,
                ),
            )
            connection.execute(
                "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    str(uuid4()),
                    request_id,
                    1,
                    _digest(cleaned, attached),
                    f"local operator, uid={os.geteuid()}",
                    now,
                    "created",
                ),
            )
            return self._get(connection, request_id)

    def update(
        self,
        request_id: str,
        expected_revision: int,
        fields: Mapping[str, object],
        *,
        attachments: Sequence[Mapping[str, object]] | None = None,
    ) -> IntakeRequest:
        self._write()
        cleaned = validate_fields(fields)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            original = self._get(connection, request_id)
            self._expected(original, expected_revision)
            if original.state not in {"draft", "approved"}:
                raise IntakeError("Reopen a rejected request before editing")
            attached = (
                original.attachments
                if attachments is None
                else _attachments(attachments, request_id)
            )
            revision = original.revision + 1
            now = datetime.now(UTC).isoformat()
            connection.execute(
                "INSERT INTO intake_revisions VALUES (?,?,?,?)",
                (request_id, revision, _json(cleaned), _json(attached)),
            )
            connection.execute(
                "UPDATE intake_requests SET "
                "revision=?,state='draft',sync_status='not_synced',updated_at=?,"
                "approved_revision=NULL,approval_hash=NULL "
                "WHERE request_id=?",
                (revision, now, request_id),
            )
            connection.execute(
                "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    str(uuid4()),
                    request_id,
                    revision,
                    _digest(cleaned, attached),
                    f"local operator (self-approval), uid={os.geteuid()}",
                    now,
                    "edited_approval_invalidated"
                    if original.state == "approved"
                    else "edited",
                ),
            )
            return self._get(connection, request_id)

    @staticmethod
    def _expected(request: IntakeRequest, expected_revision: int) -> None:
        if type(expected_revision) is not int or request.revision != expected_revision:
            raise IntakeError("Request changed; reload before continuing")

    def approve(self, request_id: str, expected_revision: int) -> IntakeRequest:
        require_supported_platform()
        self._write()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            request = self._get(connection, request_id)
            self._expected(request, expected_revision)
            self._verify_evidence(request)
            if request.state != "draft":
                raise IntakeError("Only a draft request can be approved")
            decided = datetime.now(UTC).isoformat()
            actor = f"local operator (self-approval), uid={os.geteuid()}"
            content_hash = _digest(request.fields, request.attachments)
            connection.execute(
                "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,'approved',NULL)",
                (
                    str(uuid4()),
                    request_id,
                    request.revision,
                    content_hash,
                    actor,
                    decided,
                ),
            )
            connection.execute(
                "UPDATE intake_requests SET "
                "state='approved',approved_revision=?,approval_hash=?,updated_at=? "
                "WHERE request_id=?",
                (
                    request.revision,
                    content_hash,
                    decided,
                    request_id,
                ),
            )
            return self._get(connection, request_id)

    def transition(
        self, request_id: str, expected_revision: int, target_state: str, *, reason: str
    ) -> IntakeRequest:
        self._write()
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 500
            or any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in reason)
        ):
            raise IntakeError("A bounded single-line decision reason is required")
        allowed = {
            ("draft", "rejected"),
            ("draft", "cancelled"),
            ("approved", "rejected"),
            ("approved", "cancelled"),
            ("rejected", "draft"),
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            original = self._get(connection, request_id)
            self._expected(original, expected_revision)
            if (original.state, target_state) not in allowed:
                raise IntakeError("Invalid request state transition")
            revision = original.revision + 1
            now = datetime.now(UTC).isoformat()
            connection.execute(
                "INSERT INTO intake_revisions VALUES (?,?,?,?)",
                (
                    request_id,
                    revision,
                    _json(original.fields),
                    _json(original.attachments),
                ),
            )
            connection.execute(
                "UPDATE intake_requests SET "
                "revision=?,state=?,sync_status='not_synced',updated_at=?,"
                "approved_revision=NULL,approval_hash=NULL "
                "WHERE request_id=?",
                (revision, target_state, now, request_id),
            )
            decision = "reopened" if target_state == "draft" else target_state
            connection.execute(
                "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    request_id,
                    revision,
                    _digest(original.fields, original.attachments),
                    f"local operator, uid={os.geteuid()}",
                    now,
                    decision,
                    reason.strip(),
                ),
            )
            return self._get(connection, request_id)

    def audit_history(self, request_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            self._get(connection, request_id)
            rows = connection.execute(
                "SELECT "
                "decision_id,revision,content_hash,actor,decided_at,decision,reason "
                ""
                "FROM intake_approvals WHERE request_id=? "
                "ORDER BY decided_at,decision_id",
                (request_id,),
            ).fetchall()
            return tuple(_audit_row(connection, request_id, row) for row in rows)

    def export(self, request_id: str, expected_revision: int) -> dict[str, object]:
        self._write()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            request = self._get(connection, request_id)
            self._expected(request, expected_revision)
            self._verify_evidence(request)
            if request.state != "approved":
                raise IntakeError("Approve the current revision before export")
            fields = {
                target: request.fields[source]
                for source, target in FIELD_MAPPING.items()
                if source != "preferredDate" or request.fields[source]
            }
            fields.update(
                {
                    "Title": "Pending",
                    "Source": "EDN OS Manual",
                    "SubmittedAt": request.created_at,
                    "ContractVersion": "1.0",
                    "Status": "New",
                }
            )
            connection.execute(
                "UPDATE intake_requests SET sync_status='dry_run',updated_at=? "
                "WHERE request_id=?",
                (datetime.now(UTC).isoformat(), request_id),
            )
            return {
                "fields": fields,
                "dry_run": True,
                "sync_status": "dry_run",
                "request_id": request_id,
                "revision": request.revision,
                "content_hash": _digest(request.fields, request.attachments),
                "attachment_manifest": request.attachments,
                "target": {
                    "integration": "sharepoint",
                    "list_contract": "Job Requests",
                    "live_status": "unverified",
                },
                "not_ready": [
                    "Live target identifiers are not configured",
                    "Current source permissions are unverified",
                    "Live list schema compatibility is unverified",
                    "Dry run performs no remote write",
                ],
                "approval": {
                    "revision": request.revision,
                    "content_hash": _digest(request.fields, request.attachments),
                    "actor": request.approval_actor,
                    "timestamp": request.approval_timestamp,
                },
                "submission_id": self._submission_id(connection, request_id),
                "idempotency_key": self._submission_id(connection, request_id),
                "source_provenance": {
                    "source_type": "manual",
                    "source": "EDN OS Manual",
                },
            }

    @staticmethod
    def _submission_id(connection: sqlite3.Connection, request_id: str) -> str:
        row = connection.execute(
            "SELECT submission_id FROM intake_submissions WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise IntakeError("Request submission receipt is missing")
        return _identity(row[0])

    def _verify_evidence(self, request: IntakeRequest) -> None:
        if not request.attachments and self.evidence_root is None:
            return
        if self.evidence_root is None:
            raise IntakeError("Configure protected evidence storage before approval")
        verify_evidence(self.evidence_root, request.request_id, request.attachments)
