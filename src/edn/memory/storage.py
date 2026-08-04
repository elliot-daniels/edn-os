"""SQLite persistence for canonical email records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from edn.memory.models import EmailRecord

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    source_record_key TEXT NOT NULL UNIQUE,
    folder_path TEXT NOT NULL,
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipients_to TEXT NOT NULL,
    recipients_cc TEXT NOT NULL,
    recipients_bcc TEXT NOT NULL,
    sent_at TEXT,
    received_at TEXT,
    message_id TEXT,
    body_text TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
    subject, sender, body_text, content='emails', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS emails_after_insert AFTER INSERT ON emails BEGIN
    INSERT INTO emails_fts(rowid, subject, sender, body_text)
    VALUES (new.id, new.subject, new.sender, new.body_text);
END;
"""

class SQLiteEmailStore:
    """Persist and search email records in SQLite."""

    def __init__(
        self, database_path: str | Path, *, read_only: bool = False
    ) -> None:
        self._database_path = Path(database_path)
        self._read_only = read_only

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._read_only:
            database_uri = self._database_path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(database_uri, uri=True)
        else:
            connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            if not self._read_only:
                connection.commit()
        finally:
            connection.close()

    def initialise(self) -> None:
        """Create the database schema."""
        if self._read_only:
            raise sqlite3.OperationalError("store is read-only")
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def add(self, record: EmailRecord) -> bool:
        """Insert a record; return False when its source key already exists."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO emails (
                    source_record_key, folder_path, subject, sender,
                    recipients_to, recipients_cc, recipients_bcc,
                    sent_at, received_at, message_id, body_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.source_record_key,
                    record.folder_path,
                    record.subject,
                    record.sender,
                    json.dumps(record.recipients_to),
                    json.dumps(record.recipients_cc),
                    json.dumps(record.recipients_bcc),
                    _datetime_to_text(record.sent_at),
                    _datetime_to_text(record.received_at),
                    record.message_id,
                    record.body_text,
                ),
            )
            return cursor.rowcount == 1

    def get(self, source_record_key: str) -> EmailRecord | None:
        """Retrieve one record by source key."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM emails WHERE source_record_key = ?",
                (source_record_key,),
            ).fetchone()
        return _row_to_record(row) if row is not None else None

    def count(self) -> int:
        """Return the number of stored records."""
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM emails").fetchone()
        return 0 if row is None else int(row["total"])

    def search(self, query: str, *, limit: int = 20) -> list[EmailRecord]:
        """Search subject, sender and body using FTS5."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT emails.*
                FROM emails_fts
                JOIN emails ON emails.id = emails_fts.rowid
                WHERE emails_fts MATCH ?
                ORDER BY bm25(emails_fts)
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

def _text_to_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None

def _decode_addresses(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(
        isinstance(item, str) for item in decoded
    ):
        raise ValueError("stored recipient data is invalid")
    return tuple(decoded)

def _row_to_record(row: sqlite3.Row) -> EmailRecord:
    return EmailRecord(
        source_record_key=str(row["source_record_key"]),
        folder_path=str(row["folder_path"]),
        subject=str(row["subject"]),
        sender=str(row["sender"]),
        recipients_to=_decode_addresses(str(row["recipients_to"])),
        recipients_cc=_decode_addresses(str(row["recipients_cc"])),
        recipients_bcc=_decode_addresses(str(row["recipients_bcc"])),
        sent_at=_text_to_datetime(row["sent_at"]),
        received_at=_text_to_datetime(row["received_at"]),
        message_id=row["message_id"],
        body_text=str(row["body_text"]),
    )
