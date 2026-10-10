"""Local reviewed Work Intake; export is a dry run with no external transport."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
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
from edn.operations.models import event_identity_key

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


def _duplicate_fingerprint(fields: Mapping[str, str]) -> str:
    """Possible-work signal only; never a source or submission identity."""
    identifying = (
        "company",
        "contactName",
        "siteLocation",
        "reference",
        "preferredDate",
    )
    normalized = [
        " ".join(unicodedata.normalize("NFKC", fields[name]).casefold().split())
        for name in identifying
    ]
    return hashlib.sha256(_json(["possible-work-v1", normalized]).encode()).hexdigest()


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
                "source_changed",
                "source_resolved",
                "duplicate_linked",
            }
        ):
            raise ValueError
        if decision in {
            "rejected",
            "cancelled",
            "reopened",
            "source_changed",
            "source_resolved",
            "duplicate_linked",
        }:
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
    source_type: str = "manual"
    source_pending: bool = False


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
'edited_approval_invalidated','rejected','cancelled','reopened',
'source_changed','source_resolved','duplicate_linked')),
reason TEXT
)"""


BASE_APPROVALS_DDL = APPROVALS_DDL.replace(
    "'reopened',\n'source_changed','source_resolved','duplicate_linked'))",
    "'reopened'))",
)


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


SOURCE_DDL = """CREATE TABLE intake_sources (
source_key TEXT PRIMARY KEY NOT NULL,
request_id TEXT NOT NULL UNIQUE REFERENCES intake_requests(request_id),
identity TEXT NOT NULL,
source_revision INTEGER NOT NULL,
source_hash TEXT NOT NULL,
pending INTEGER NOT NULL CHECK(pending IN (0,1))
)"""
SOURCE_HISTORY_DDL = """CREATE TABLE intake_source_history (
source_key TEXT NOT NULL REFERENCES intake_sources(source_key),
source_revision INTEGER NOT NULL,
payload TEXT NOT NULL,
canonical_hash TEXT NOT NULL,
PRIMARY KEY(source_key,source_revision)
)"""
DUPLICATE_DDL = """CREATE TABLE intake_duplicate_decisions (
decision_id TEXT PRIMARY KEY NOT NULL,
request_id TEXT NOT NULL REFERENCES intake_requests(request_id),
other_id TEXT NOT NULL REFERENCES intake_requests(request_id),
request_hash TEXT NOT NULL,
other_hash TEXT NOT NULL,
request_revision INTEGER NOT NULL,
other_revision INTEGER NOT NULL,
decision TEXT NOT NULL CHECK(decision IN ('distinct','same_work')),
actor TEXT NOT NULL,
decided_at TEXT NOT NULL,
reason TEXT NOT NULL
)"""
LINKS_DDL = """CREATE TABLE intake_work_links (
alias_id TEXT PRIMARY KEY NOT NULL REFERENCES intake_requests(request_id),
canonical_id TEXT NOT NULL REFERENCES intake_requests(request_id)
)"""


def _source_identity(value: Mapping[str, str], external_id: str) -> dict[str, str]:
    expected = {
        "source_system",
        "source_account",
        "site_id",
        "list_id",
        "native_item_id",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise IntakeError("Explicit synthetic source identity is required")
    identity = dict(value)
    if any(
        not isinstance(item, str)
        or not item.strip()
        or item != item.strip()
        or len(item) > 200
        or any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in item)
        for item in identity.values()
    ):
        raise IntakeError("Invalid synthetic source identity")
    if (
        identity["source_system"] != "sharepoint"
        or identity["native_item_id"] != external_id
    ):
        raise IntakeError("Synthetic native source identity does not match")
    return identity


def _source_contract(payload: Mapping[str, object]) -> tuple[dict[str, str], str]:
    try:
        if (
            not isinstance(payload, Mapping)
            or set(payload)
            != INPUT_FIELDS | {"source", "submittedAt", "contractVersion"}
            or payload["source"] != "EDN Systems Website"
            or payload["contractVersion"] != "1.0"
            or len(_json(dict(payload)).encode()) > 32768
        ):
            raise ValueError
        submitted = payload["submittedAt"]
        if not isinstance(submitted, str):
            raise ValueError
        timestamp = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
        if timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise ValueError
        fields = validate_fields({name: payload[name] for name in INPUT_FIELDS})
        digest = hashlib.sha256(
            _json([fields, payload["source"], timestamp.isoformat()]).encode()
        ).hexdigest()
        return fields, digest
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise IntakeError("Invalid synthetic website contract") from None


MAX_DATABASE_BYTES = 100_000_000
_EMAIL_ANSWER_BARRIER = "Synthetic email answer edit started; source review is required"


def _email_answer_staged(connection: sqlite3.Connection, request_id: str) -> bool:
    row = connection.execute(
        "SELECT reason FROM intake_approvals WHERE request_id=? "
        "AND decision='source_changed' ORDER BY rowid DESC LIMIT 1",
        (request_id,),
    ).fetchone()
    return bool(row == (_EMAIL_ANSWER_BARRIER,))


def _record_identity(value: Mapping[str, str], external_id: str) -> dict[str, str]:
    """Keep website identities strict; email uses its own source namespace."""
    if not isinstance(value, Mapping) or value.get("source_system") != "email":
        return _source_identity(value, external_id)
    if set(value) != {
        "source_system",
        "event_source",
        "source_account",
        "native_item_id",
    }:
        raise IntakeError("Invalid synthetic email source identity")
    if (
        any(
            not isinstance(v, str)
            or not v.strip()
            or v != v.strip()
            or len(v) > 200
            or any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in v)
            for v in value.values()
        )
        or not value["event_source"].startswith("synthetic_")
        or value["native_item_id"] != external_id
    ):
        raise IntakeError("Invalid synthetic email source identity")
    return dict(value)


def _record_contract(payload: Mapping[str, object]) -> tuple[dict[str, str], str]:
    if not isinstance(payload, Mapping) or payload.get("source") != "EDN OS Email":
        return _source_contract(payload)
    try:
        if (
            set(payload)
            != INPUT_FIELDS
            | {"source", "submittedAt", "contractVersion", "email_receipt"}
            or payload["contractVersion"] != "1.0"
        ):
            raise ValueError
        receipt = payload["email_receipt"]
        if not isinstance(receipt, dict) or set(receipt) != {
            "identity",
            "event_source_key",
            "source_hash",
            "draft_revision",
            "assessment_version",
            "facts",
            "answers",
            "defaults",
        }:
            raise ValueError
        identity = _record_identity(
            receipt["identity"], receipt["identity"]["native_item_id"]
        )
        if identity["source_system"] != "email" or receipt[
            "event_source_key"
        ] != event_identity_key(
            identity["event_source"],
            identity["source_account"],
            identity["native_item_id"],
        ):
            raise ValueError
        if (
            type(receipt["draft_revision"]) is not int
            or receipt["draft_revision"] < 1
            or type(receipt["assessment_version"]) is not int
            or receipt["assessment_version"] < 1
            or re.fullmatch(r"[0-9a-f]{64}", receipt["source_hash"]) is None
            or not isinstance(receipt["facts"], list)
            or not isinstance(receipt["answers"], dict)
            or receipt["defaults"]
            != {"serviceRequired": "Other / not sure", "urgency": "Routine"}
        ):
            raise ValueError
        for fact in receipt["facts"]:
            if not isinstance(fact, dict) or set(fact) != {
                "field",
                "value",
                "quote",
                "source_key",
                "basis",
            }:
                raise ValueError
            if (
                fact["source_key"] != receipt["event_source_key"]
                or fact["basis"] != "email_reported"
            ):
                raise ValueError
            if any(not isinstance(fact[n], str) for n in ("field", "value", "quote")):
                raise ValueError
        for answer in receipt["answers"].values():
            if not isinstance(answer, dict) or set(answer) != {
                "value",
                "basis",
                "actor",
            }:
                raise ValueError
            if answer["basis"] != "operator_confirmed" or any(
                not isinstance(answer[n], str) for n in ("value", "actor")
            ):
                raise ValueError
        submitted = payload["submittedAt"]
        if not isinstance(submitted, str):
            raise ValueError
        timestamp = datetime.fromisoformat(submitted)
        if timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise ValueError
        fields = validate_fields({name: payload[name] for name in INPUT_FIELDS})
        encoded = _json(dict(payload)).encode()
        if len(encoded) > 32768:
            raise ValueError
        return fields, hashlib.sha256(encoded).hexdigest()
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise IntakeError("Invalid synthetic email contract") from None


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
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        expected = sorted(
            [
                *expected,
                (
                    "intake_approvals",
                    APPROVALS_DDL if version == 3 else BASE_APPROVALS_DDL,
                ),
            ]
        )
        if version in {2, 3}:
            expected = sorted(
                [
                    *expected,
                    ("intake_submissions", SUBMISSIONS_DDL),
                    ("intake_intent", INTENT_DDL),
                ]
            )
        if version == 3:
            expected = sorted(
                [
                    *expected,
                    ("intake_sources", SOURCE_DDL),
                    ("intake_source_history", SOURCE_HISTORY_DDL),
                    ("intake_duplicate_decisions", DUPLICATE_DDL),
                    ("intake_work_links", LINKS_DDL),
                ]
            )
        if rows != expected or version not in {1, 2, 3}:
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
            if version == 3:
                return
            connection.execute("BEGIN IMMEDIATE")
            if version == 0:
                connection.execute(DDL)
                connection.execute(REVISIONS_DDL)
                connection.execute(APPROVALS_DDL)
            if version < 2:
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
            if version in {1, 2}:
                connection.execute(
                    "ALTER TABLE intake_approvals RENAME TO intake_approvals_previous"
                )
                connection.execute(APPROVALS_DDL)
                connection.execute(
                    "INSERT INTO intake_approvals SELECT * "
                    "FROM intake_approvals_previous ORDER BY rowid"
                )
                connection.execute("DROP TABLE intake_approvals_previous")
            connection.execute(SOURCE_DDL)
            connection.execute(SOURCE_HISTORY_DDL)
            connection.execute(DUPLICATE_DDL)
            connection.execute(LINKS_DDL)
            connection.execute("PRAGMA user_version=3")
            assert isinstance(connection, _ProtectedConnection)
            connection.initialise_snapshot = True

    @staticmethod
    def _submission_schema(connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone()[0] not in {2, 3}:
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
            else {
                "edited",
                "edited_approval_invalidated",
                "reopened",
                "source_changed",
                "source_resolved",
                "duplicate_linked",
            },
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
        provenance = IntakeStore._provenance(connection, request_id)
        if row[2] == "approved" and provenance.get("source_pending"):
            raise IntakeError("Approved request has unresolved source facts")
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
            str(provenance["source_type"]),
            bool(provenance.get("source_pending", False)),
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
                "fields=excluded.fields,attachments=excluded.attachments,"
                "initial_hash=excluded.initial_hash,request_id=excluded.request_id",
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
            if self._canonical(connection, request_id) != request_id:
                raise IntakeError(
                    "Linked request is read-only; edit the canonical work"
                )
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
            self._review_gate(connection, request)
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
            if self._canonical(connection, request_id) != request_id:
                raise IntakeError("Linked request lifecycle belongs to canonical work")
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
            return self._export_locked(connection, request_id, expected_revision)

    @contextmanager
    def authorise_delivery(self, payload: Mapping[str, object]) -> Iterator[None]:
        """Hold the intake lock through delivery of the exact current approval."""
        request_id = payload.get("request_id")
        revision = payload.get("revision")
        if not isinstance(request_id, str) or type(revision) is not int:
            raise IntakeError("Delivery does not match the current approval")
        with self._connect() as connection:
            current = self._export_locked(
                connection, request_id, revision, mark_dry_run=False
            )
            for key in (
                "request_id",
                "revision",
                "content_hash",
                "idempotency_key",
                "submission_id",
                "approval",
                "fields",
                "source_provenance",
                "target",
            ):
                if payload.get(key) != current.get(key):
                    raise IntakeError("Delivery does not match the current approval")
            manifest = payload.get("attachment_manifest")
            if isinstance(manifest, dict):
                manifest = manifest.get("files")
            if (
                not isinstance(manifest, (list, tuple))
                or tuple(manifest) != current["attachment_manifest"]
            ):
                raise IntakeError(
                    "Delivery evidence does not match the current approval"
                )
            if current.get("operation", "create_proposal") != "create_proposal":
                raise IntakeError("Existing source work cannot create a synthetic item")
            yield

    def _export_locked(
        self,
        connection: sqlite3.Connection,
        request_id: str,
        expected_revision: int,
        *,
        mark_dry_run: bool = True,
    ) -> dict[str, object]:
        connection.execute("BEGIN IMMEDIATE")
        request = self._get(connection, request_id)
        self._expected(request, expected_revision)
        self._review_gate(connection, request)
        self._verify_evidence(request)
        if request.state != "approved":
            raise IntakeError("Approve the current revision before export")
        provenance = self._group_provenance(connection, request_id)
        fields = {
            target: request.fields[source]
            for source, target in FIELD_MAPPING.items()
            if source != "preferredDate" or request.fields[source]
        }
        fields.update(
            {
                "Title": "Pending",
                "Source": str(provenance["source"]),
                "SubmittedAt": str(provenance["submitted_at"])
                if "submitted_at" in provenance
                else request.created_at,
                "ContractVersion": "1.0",
                "Status": "New",
            }
        )
        if mark_dry_run:
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
            "operation": (
                "reference_existing"
                if provenance["source_type"] == "synthetic_import"
                else "create_proposal"
            ),
            "content_hash": _digest(request.fields, request.attachments),
            "attachment_manifest": request.attachments,
            "target": {
                "integration": "sharepoint",
                "list_contract": "Job Requests",
                "live_status": "unverified",
                **{
                    name: value
                    for name, value in provenance.items()
                    if provenance["source_type"] == "synthetic_import"
                    and name
                    in {
                        "source_system",
                        "source_account",
                        "site_id",
                        "list_id",
                        "native_item_id",
                    }
                },
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
            "source_provenance": provenance,
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

    @staticmethod
    def _source_schema(connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA user_version").fetchone() != (3,):
            raise IntakeError("Initialize synthetic source review explicitly")

    def import_contract(
        self,
        payload: Mapping[str, object],
        external_id: str,
        *,
        source_identity: Mapping[str, str],
    ) -> IntakeRequest:
        self._write()
        identity = _source_identity(source_identity, external_id)
        _source_contract(payload)
        return self._import_source(payload, identity)

    def _import_source(
        self, payload: Mapping[str, object], identity: Mapping[str, str]
    ) -> IntakeRequest:
        self._write()
        identity = _record_identity(identity, identity["native_item_id"])
        fields, source_hash = _record_contract(payload)
        if (identity["source_system"] == "email") != (
            payload["source"] == "EDN OS Email"
        ):
            raise IntakeError("Source contract and identity disagree")
        if payload["source"] == "EDN OS Email":
            receipt = payload["email_receipt"]
            if not isinstance(receipt, dict) or receipt["identity"] != identity:
                raise IntakeError("Source contract and identity disagree")
        source_key = hashlib.sha256(_json(identity).encode()).hexdigest()
        with self._connect() as connection:
            self._source_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT request_id,source_revision,source_hash FROM intake_sources "
                "WHERE source_key=?",
                (source_key,),
            ).fetchone()
            if existing:
                request = self._get(connection, existing[0])
                if existing[2] == source_hash:
                    if request.source_pending and _email_answer_staged(
                        connection, request.request_id
                    ):
                        # Current draft was reread under its lock. An interrupted
                        # answer left it unchanged; source review can now resume.
                        self._record_revision(
                            connection,
                            request,
                            request.fields,
                            "source_changed",
                            "Synthetic email answer recovery verified unchanged source",
                        )
                        return self._get(connection, request.request_id)
                    return request
                revision = existing[1] + 1
                connection.execute(
                    "INSERT INTO intake_source_history VALUES (?,?,?,?)",
                    (source_key, revision, _json(dict(payload)), source_hash),
                )
                connection.execute(
                    "UPDATE intake_sources SET "
                    "source_revision=?,source_hash=?,pending=1 WHERE source_key=?",
                    (revision, source_hash, source_key),
                )
                if request.state in {"draft", "approved"}:
                    self._record_revision(
                        connection,
                        request,
                        request.fields,
                        "source_changed",
                        "Synthetic source facts changed; "
                        "operator resolution is required",
                    )
                canonical = self._canonical(connection, request.request_id)
                if canonical != request.request_id:
                    parent = self._get(connection, canonical)
                    if parent.state in {"draft", "approved"}:
                        self._record_revision(
                            connection,
                            parent,
                            parent.fields,
                            "source_changed",
                            "Linked synthetic source facts changed; "
                            "operator resolution is required",
                        )
                return self._get(connection, request.request_id)
            request_id = str(uuid4())
            submission_id = str(uuid5(NAMESPACE_URL, "edn-intake-source:" + source_key))
            now = datetime.now(UTC).isoformat()
            connection.execute(
                "INSERT INTO intake_requests VALUES "
                "(?,1,'draft','not_synced',?,?,NULL,NULL,1)",
                (request_id, now, now),
            )
            connection.execute(
                "INSERT INTO intake_revisions VALUES (?,1,?,'[]')",
                (request_id, _json(fields)),
            )
            connection.execute(
                "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    str(uuid4()),
                    request_id,
                    1,
                    _digest(fields, ()),
                    f"local operator, uid={os.geteuid()}",
                    now,
                    "created",
                ),
            )
            connection.execute(
                "INSERT INTO intake_submissions VALUES (?,?,?,?,?)",
                (submission_id, _json(fields), "[]", _digest(fields, ()), request_id),
            )
            connection.execute(
                "INSERT INTO intake_sources VALUES (?,?,?,?,?,0)",
                (source_key, request_id, _json(identity), 1, source_hash),
            )
            connection.execute(
                "INSERT INTO intake_source_history VALUES (?,1,?,?)",
                (source_key, _json(dict(payload)), source_hash),
            )
            return self._get(connection, request_id)

    def stage_email_answer(
        self,
        identity: Mapping[str, str],
        source_hash: str,
        draft_revision: int,
        field: str,
        value: str,
    ) -> bool:
        """Publish a durable approval barrier before a linked draft answer changes.

        Caller holds the email draft lock. Pending source review survives an
        interrupted second-store write; no stale approval can deliver meanwhile.
        """
        self._write()
        identity = _record_identity(identity, identity.get("native_item_id", ""))
        if identity["source_system"] != "email":
            raise IntakeError("Only synthetic email answers use this guard")
        if type(draft_revision) is not int or draft_revision < 1:
            raise IntakeError("Invalid email draft revision")
        source_key = hashlib.sha256(_json(identity).encode()).hexdigest()
        with self._connect() as connection:
            self._source_schema(connection)
            row = connection.execute(
                "SELECT request_id FROM intake_sources WHERE source_key=?",
                (source_key,),
            ).fetchone()
            if row is None:
                return False
            request = self._get(connection, row[0])
            provenance = self._provenance(connection, row[0])
            receipt = provenance["email_receipt"]
            if (
                not isinstance(receipt, dict)
                or receipt["source_hash"] != source_hash
                or receipt["draft_revision"] > draft_revision
            ):
                raise IntakeError(
                    "Refresh and resolve canonical source before answering"
                )
            if request.state not in {"draft", "approved"}:
                raise IntakeError("Reopen canonical work before editing source answers")
            canonical_id = self._canonical(connection, request.request_id)
            affected = [request]
            if canonical_id != request.request_id:
                affected.append(self._get(connection, canonical_id))
            if any(item.state not in {"draft", "approved"} for item in affected):
                raise IntakeError("Reopen canonical work before editing source answers")
            canonical_field = "preferredDate" if field == "requested_date" else field
            if canonical_field in INPUT_FIELDS:
                validate_fields({**request.fields, canonical_field: value})
            if request.source_pending:
                if not _email_answer_staged(connection, request.request_id):
                    raise IntakeError("Resolve canonical source before answering")
                return True
            if receipt["draft_revision"] != draft_revision:
                raise IntakeError("Refresh canonical source before answering")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE intake_sources SET pending=1 WHERE source_key=?", (source_key,)
            )
            for item in affected:
                self._record_revision(
                    connection,
                    item,
                    item.fields,
                    "source_changed",
                    _EMAIL_ANSWER_BARRIER,
                )
            return True

    @staticmethod
    def _record_revision(
        connection: sqlite3.Connection,
        request: IntakeRequest,
        fields: Mapping[str, object],
        decision: str,
        reason: str,
    ) -> None:
        cleaned = validate_fields(fields)
        revision = request.revision + 1
        now = datetime.now(UTC).isoformat()
        connection.execute(
            "INSERT INTO intake_revisions VALUES (?,?,?,?)",
            (request.request_id, revision, _json(cleaned), _json(request.attachments)),
        )
        connection.execute(
            "UPDATE intake_requests SET "
            "revision=?,state='draft',sync_status='not_synced',updated_at=?,"
            "approved_revision=NULL,approval_hash=NULL WHERE request_id=?",
            (revision, now, request.request_id),
        )
        connection.execute(
            "INSERT INTO intake_approvals VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                request.request_id,
                revision,
                _digest(cleaned, request.attachments),
                f"local operator, uid={os.geteuid()}",
                now,
                decision,
                reason,
            ),
        )

    def resolve_source_change(
        self, request_id: str, expected_revision: int, *, decision: str, reason: str
    ) -> IntakeRequest:
        self._write()
        if (
            decision not in {"keep_local", "apply_source"}
            or not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 500
            or any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in reason)
        ):
            raise IntakeError(
                "Explicit source resolution and bounded reason are required"
            )
        with self._connect() as connection:
            self._source_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            request = self._get(connection, request_id)
            self._expected(request, expected_revision)
            if request.state != "draft":
                raise IntakeError("Reopen a rejected request before source resolution")
            row = connection.execute(
                "SELECT source_key,source_revision,pending FROM intake_sources "
                "WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None or row[2] != 1:
                raise IntakeError("No unresolved source update exists")
            if _email_answer_staged(connection, request_id):
                raise IntakeError("Refresh the email draft before source resolution")
            payload = json.loads(
                connection.execute(
                    "SELECT payload FROM intake_source_history WHERE source_key=? AND "
                    "source_revision=?",
                    (row[0], row[1]),
                ).fetchone()[0]
            )
            source_fields, _ = _record_contract(payload)
            canonical = self._canonical(connection, request_id)
            if canonical != request_id:
                parent = self._get(connection, canonical)
                if parent.state not in {"draft", "approved"}:
                    raise IntakeError(
                        "Reopen canonical work before resolving source facts"
                    )
                if decision == "apply_source":
                    self._record_revision(
                        connection,
                        parent,
                        source_fields,
                        "source_resolved",
                        reason.strip(),
                    )
            self._record_revision(
                connection,
                request,
                source_fields if decision == "apply_source" else request.fields,
                "source_resolved",
                reason.strip(),
            )
            connection.execute(
                "UPDATE intake_sources SET pending=0 WHERE request_id=?", (request_id,)
            )
            return self._get(connection, request_id)

    @staticmethod
    def _canonical(connection: sqlite3.Connection, request_id: str) -> str:
        if connection.execute("PRAGMA user_version").fetchone() != (3,):
            return request_id
        visited = set()
        while request_id not in visited:
            visited.add(request_id)
            row = connection.execute(
                "SELECT canonical_id FROM intake_work_links WHERE alias_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                return request_id
            audit = connection.execute(
                "SELECT decision_id,other_id,request_hash,other_hash,request_revision,"
                "other_revision,actor,decided_at,reason "
                "FROM intake_duplicate_decisions "
                "WHERE request_id=? AND decision='same_work' "
                "ORDER BY rowid DESC LIMIT 1",
                (request_id,),
            ).fetchone()
            try:
                if audit is None or audit[1] != row[0]:
                    raise ValueError
                _identity(audit[0])
                if (
                    re.fullmatch(r"local operator, uid=(0|[1-9][0-9]*)", audit[6])
                    is None
                    or datetime.fromisoformat(audit[7]).utcoffset()
                    != UTC.utcoffset(datetime.fromisoformat(audit[7]))
                    or not isinstance(audit[8], str)
                    or not audit[8].strip()
                ):
                    raise ValueError
                for identifier, revision, expected_hash in (
                    (request_id, audit[4], audit[2]),
                    (row[0], audit[5], audit[3]),
                ):
                    if type(revision) is not int or revision < 1:
                        raise ValueError
                    original = connection.execute(
                        "SELECT fields,attachments FROM intake_revisions "
                        "WHERE request_id=? AND revision=?",
                        (identifier, revision),
                    ).fetchone()
                    if (
                        original is None
                        or _digest(
                            validate_fields(json.loads(original[0])),
                            _attachments(json.loads(original[1]), identifier),
                        )
                        != expected_hash
                    ):
                        raise ValueError
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                raise IntakeError("Stored work linkage audit is invalid") from None
            request_id = row[0]
        raise IntakeError("Work linkage is inconsistent")

    @staticmethod
    def _initial_fields(
        connection: sqlite3.Connection, request_id: str
    ) -> dict[str, str]:
        row = connection.execute(
            "SELECT fields FROM intake_submissions WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None:
            raise IntakeError("Original request receipt is missing")
        try:
            return validate_fields(json.loads(row[0]))
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise IntakeError("Original receipt facts are invalid") from None

    def duplicate_candidates(self, request_id: str) -> tuple[IntakeRequest, ...]:
        with self._connect() as connection:
            self._source_schema(connection)
            request = self._get(connection, request_id)
            return self._candidates(connection, request)

    def _candidates(
        self, connection: sqlite3.Connection, request: IntakeRequest
    ) -> tuple[IntakeRequest, ...]:
        fingerprints = self._fingerprints(connection, request)
        result = []
        for (other_id,) in connection.execute(
            "SELECT request_id FROM intake_requests WHERE request_id<>?",
            (request.request_id,),
        ).fetchall():
            if self._canonical(connection, other_id) == self._canonical(
                connection, request.request_id
            ):
                continue
            other = self._get(connection, other_id)
            if fingerprints.isdisjoint(self._fingerprints(connection, other)):
                continue
            decision = connection.execute(
                "SELECT "
                "request_id,request_hash,other_hash,decision,request_revision,"
                "other_revision,decision_id,actor,decided_at,reason FROM "
                "intake_duplicate_decisions WHERE (request_id=? AND other_id=?) OR "
                "(request_id=? AND other_id=?) ORDER BY rowid DESC LIMIT 1",
                (request.request_id, other_id, other_id, request.request_id),
            ).fetchone()
            if decision:
                try:
                    _identity(decision[6])
                    if (
                        decision[3] not in {"distinct", "same_work"}
                        or re.fullmatch(
                            r"local operator, uid=(0|[1-9][0-9]*)", decision[7]
                        )
                        is None
                        or datetime.fromisoformat(decision[8]).utcoffset()
                        != UTC.utcoffset(datetime.fromisoformat(decision[8]))
                        or not isinstance(decision[9], str)
                        or not decision[9].strip()
                    ):
                        raise ValueError
                except (ValueError, TypeError, AttributeError):
                    raise IntakeError("Stored duplicate decision is invalid") from None
            if decision and decision[3] == "distinct":
                hashes = (
                    _digest(request.fields, request.attachments),
                    _digest(other.fields, other.attachments),
                )
                stored = (
                    (decision[1], decision[2])
                    if decision[0] == request.request_id
                    else (decision[2], decision[1])
                )
                versions = (request.revision, other.revision)
                stored_versions = (
                    (decision[4], decision[5])
                    if decision[0] == request.request_id
                    else (decision[5], decision[4])
                )
                if hashes == stored and versions == stored_versions:
                    continue
            result.append(other)
        return tuple(result)

    def _fingerprints(
        self, connection: sqlite3.Connection, request: IntakeRequest
    ) -> set[str]:
        return {
            _duplicate_fingerprint(request.fields),
            _duplicate_fingerprint(
                self._initial_fields(connection, request.request_id)
            ),
        }

    def resolve_duplicate(
        self,
        request_id: str,
        other_id: str,
        expected_revision: int,
        *,
        decision: str,
        reason: str,
    ) -> None:
        self._write()
        if (
            decision not in {"distinct", "same_work"}
            or not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 500
            or any(unicodedata.category(c) in {"Cc", "Cf", "Zl", "Zp"} for c in reason)
        ):
            raise IntakeError(
                "Explicit duplicate resolution and bounded reason are required"
            )
        with self._connect() as connection:
            self._source_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            request = self._get(connection, request_id)
            other = self._get(connection, other_id)
            self._expected(request, expected_revision)
            if request_id == other_id or self._fingerprints(
                connection, request
            ).isdisjoint(self._fingerprints(connection, other)):
                raise IntakeError("Requests are not a duplicate candidate pair")
            if decision == "same_work":
                if request.state not in {"draft", "approved"} or other.state not in {
                    "draft",
                    "approved",
                }:
                    raise IntakeError("Reopen requests before linking the same work")
                canonical = self._canonical(connection, other_id)
                if canonical != other_id:
                    raise IntakeError("Select the canonical work request for linkage")
                parent = self._get(connection, canonical)
                if parent.state not in {"draft", "approved"}:
                    raise IntakeError(
                        "Reopen canonical work before linking the same work"
                    )
                if (
                    canonical == request_id
                    or self._canonical(connection, request_id) != request_id
                ):
                    raise IntakeError("Work linkage would be inconsistent")
                connection.execute(
                    "INSERT INTO intake_work_links VALUES (?,?)",
                    (request_id, canonical),
                )
                self._record_revision(
                    connection,
                    parent,
                    parent.fields,
                    "duplicate_linked",
                    reason.strip(),
                )
                self._record_revision(
                    connection,
                    request,
                    request.fields,
                    "duplicate_linked",
                    reason.strip(),
                )
            connection.execute(
                "INSERT INTO intake_duplicate_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    request_id,
                    other_id,
                    _digest(request.fields, request.attachments),
                    _digest(other.fields, other.attachments),
                    request.revision,
                    other.revision,
                    decision,
                    f"local operator, uid={os.geteuid()}",
                    datetime.now(UTC).isoformat(),
                    reason.strip(),
                ),
            )

    def _review_gate(
        self, connection: sqlite3.Connection, request: IntakeRequest
    ) -> None:
        if connection.execute("PRAGMA user_version").fetchone() != (3,):
            return
        if self._canonical(connection, request.request_id) != request.request_id:
            raise IntakeError(
                "Linked request cannot be approved or exported independently"
            )
        for source_id, pending in connection.execute(
            "SELECT request_id,pending FROM intake_sources"
        ).fetchall():
            if pending and self._canonical(connection, source_id) == request.request_id:
                raise IntakeError(
                    "Resolve changed source facts before approval or export"
                )
        if self._candidates(connection, request):
            raise IntakeError(
                "Resolve potential duplicate work before approval or export"
            )

    @staticmethod
    def _provenance(
        connection: sqlite3.Connection, request_id: str
    ) -> dict[str, object]:
        if connection.execute("PRAGMA user_version").fetchone() != (3,):
            return {"source_type": "manual", "source": "EDN OS Manual"}
        row = connection.execute(
            "SELECT source_key,identity,source_revision,source_hash,pending "
            "FROM intake_sources WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if row is None:
            return {"source_type": "manual", "source": "EDN OS Manual"}
        try:
            raw_identity = json.loads(row[1])
            identity = _record_identity(raw_identity, raw_identity["native_item_id"])
            if (
                hashlib.sha256(_json(identity).encode()).hexdigest() != row[0]
                or type(row[2]) is not int
                or row[2] < 1
                or type(row[4]) is not int
                or row[4] not in {0, 1}
            ):
                raise ValueError
            history = connection.execute(
                "SELECT payload,canonical_hash FROM intake_source_history "
                "WHERE source_key=? AND source_revision=?",
                (row[0], row[2]),
            ).fetchone()
            if history is None:
                raise ValueError
            payload = json.loads(history[0])
            _, digest = _record_contract(payload)
            if digest != history[1] or digest != row[3]:
                raise ValueError
            if (identity["source_system"] == "email") != (
                payload["source"] == "EDN OS Email"
            ):
                raise ValueError
            if (
                identity["source_system"] == "email"
                and payload["email_receipt"]["identity"] != identity
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            raise IntakeError("Stored source provenance is invalid") from None
        return {
            "source_type": "synthetic_email"
            if identity["source_system"] == "email"
            else "synthetic_import",
            "source": payload["source"],
            "synthetic_only": True,
            **identity,
            **(
                {"email_receipt": payload["email_receipt"]}
                if identity["source_system"] == "email"
                else {}
            ),
            "source_revision": row[2],
            "source_pending": bool(row[4]),
        }

    def source_provenance(self, request_id: str) -> dict[str, object]:
        with self._connect() as connection:
            self._get(connection, request_id)
            provenance = self._provenance(connection, request_id)
            canonical = self._canonical(connection, request_id)
            return {
                **provenance,
                "canonical_work_id": canonical,
                "linked_alias": canonical != request_id,
            }

    def source_snapshot(self, request_id: str) -> dict[str, object]:
        """Read the bounded validated proposal for explicit operator review."""
        with self._connect() as connection:
            self._get(connection, request_id)
            self._source_schema(connection)
            row = connection.execute(
                "SELECT h.payload FROM intake_sources s "
                "JOIN intake_source_history h ON h.source_key=s.source_key "
                "AND h.source_revision=s.source_revision WHERE s.request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise IntakeError("Manual request has no source snapshot")
            try:
                payload = json.loads(row[0])
                fields, _ = _record_contract(payload)
                return {
                    **fields,
                    "contractVersion": "1.0",
                    "source": payload["source"],
                    "submittedAt": datetime.fromisoformat(
                        payload["submittedAt"].replace("Z", "+00:00")
                    ).isoformat(),
                }
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                raise IntakeError("Stored source snapshot is invalid") from None

    @staticmethod
    def _source_submitted(
        connection: sqlite3.Connection, request: IntakeRequest
    ) -> str:
        row = connection.execute(
            "SELECT h.payload FROM intake_sources s JOIN intake_source_history "
            "h ON h.source_key=s.source_key AND "
            "h.source_revision=s.source_revision WHERE s.request_id=?",
            (request.request_id,),
        ).fetchone()
        payload = json.loads(row[0])
        _record_contract(payload)
        return datetime.fromisoformat(
            payload["submittedAt"].replace("Z", "+00:00")
        ).isoformat()

    def _group_provenance(
        self, connection: sqlite3.Connection, request_id: str
    ) -> dict[str, object]:
        provenance = self._provenance(connection, request_id)
        if connection.execute("PRAGMA user_version").fetchone() != (3,):
            return provenance
        canonical = self._canonical(connection, request_id)
        source_ids = [
            row[0]
            for row in connection.execute(
                "SELECT request_id FROM intake_sources ORDER BY source_key"
            ).fetchall()
            if self._canonical(connection, row[0]) == canonical
        ]
        if source_ids:
            # A linked website record already exists remotely. Never let an email
            # alias turn that group into a second create proposal.
            source_ids.sort(
                key=lambda identifier: (
                    self._provenance(connection, identifier)["source_type"]
                    != "synthetic_import"
                )
            )
            provenance = self._provenance(connection, source_ids[0])
            source_request = self._get(connection, source_ids[0])
            provenance["submitted_at"] = self._source_submitted(
                connection, source_request
            )
            provenance["canonical_work_id"] = canonical
            provenance["existing_source_count"] = len(source_ids)
        return provenance
