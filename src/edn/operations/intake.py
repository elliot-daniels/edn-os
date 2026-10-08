"""Local reviewed Work Intake; export is a dry run with no external transport."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

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


def validate_fields(fields: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(fields, Mapping) or set(fields) - INPUT_FIELDS:
        raise IntakeError("Unsupported request fields")
    result: dict[str, str] = {}
    for name in INPUT_FIELDS:
        value = fields.get(name, "")
        if not isinstance(value, str):
            raise IntakeError("Request fields must be text")
        value = value.strip()
        if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise IntakeError("Request contains unsupported controls")
        if len(value.encode("utf-16-le")) // 2 > LIMITS.get(name, 100):
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
            or not 0 < item["size_bytes"] <= 10 * 1024 * 1024
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
        ):
            raise IntakeError("Invalid attachment metadata")
        result.append(item)
    if len(result) > 10 or len({item["attachment_id"] for item in result}) != len(
        result
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


DDL = """CREATE TABLE intake_requests (
request_id TEXT PRIMARY KEY NOT NULL,
revision INTEGER NOT NULL,
state TEXT NOT NULL CHECK(state IN ('draft','approved')),
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


class IntakeStore:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only

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
        if rows != expected or connection.execute("PRAGMA user_version").fetchone() != (
            1,
        ):
            raise IntakeError("Unsupported request store schema")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise IntakeError("Request store integrity is invalid")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode={'ro' if self.read_only else 'rw'}",
            uri=True,
        )
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            self._validate(connection)
        except BaseException:
            connection.close()
            raise
        return connection

    def initialise(self) -> None:
        self._write()
        if self.path.exists():
            with self._connect():
                return
        # Exclusive creation never adopts or rewrites another database.
        try:
            with self.path.open("xb"):
                pass
        except FileExistsError:
            raise IntakeError("Request store already exists") from None
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(DDL)
            connection.execute(REVISIONS_DDL)
            connection.execute("PRAGMA user_version=1")

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
            if row[2] not in {"draft", "approved"} or row[3] not in {
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

    def create(
        self,
        fields: Mapping[str, object],
        *,
        attachments: Sequence[Mapping[str, object]] = (),
    ) -> IntakeRequest:
        self._write()
        request_id = str(uuid4())
        cleaned = validate_fields(fields)
        attached = _attachments(attachments, request_id)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intake_requests VALUES "
                "(?,1,'draft','not_synced',?,?,NULL,NULL,1)",
                (request_id, now, now),
            )
            connection.execute(
                "INSERT INTO intake_revisions VALUES (?,1,?,?)",
                (request_id, _json(cleaned), _json(attached)),
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
            return self._get(connection, request_id)

    @staticmethod
    def _expected(request: IntakeRequest, expected_revision: int) -> None:
        if type(expected_revision) is not int or request.revision != expected_revision:
            raise IntakeError("Request changed; reload before continuing")

    def approve(self, request_id: str, expected_revision: int) -> IntakeRequest:
        self._write()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            request = self._get(connection, request_id)
            self._expected(request, expected_revision)
            connection.execute(
                "UPDATE intake_requests SET "
                "state='approved',approved_revision=?,approval_hash=?,updated_at=? "
                "WHERE request_id=?",
                (
                    request.revision,
                    _digest(request.fields, request.attachments),
                    datetime.now(UTC).isoformat(),
                    request_id,
                ),
            )
            return self._get(connection, request_id)

    def export(self, request_id: str, expected_revision: int) -> dict[str, object]:
        self._write()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            request = self._get(connection, request_id)
            self._expected(request, expected_revision)
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
            }
