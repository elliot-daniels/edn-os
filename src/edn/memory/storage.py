"""SQLite persistence for canonical email records."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from edn.memory.models import EmailRecord

DEFAULT_CONNECTION_TIMEOUT_SECONDS = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 30_000
DEFAULT_MAX_LOCK_RETRIES = 5
DEFAULT_RETRY_BASE_DELAY_SECONDS = 0.1

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

_INSERT_EMAIL = """
INSERT OR IGNORE INTO emails (
    source_record_key, folder_path, subject, sender,
    recipients_to, recipients_cc, recipients_bcc,
    sent_at, received_at, message_id, body_text
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

T = TypeVar("T")


class DatabaseBusyError(sqlite3.OperationalError):
    """Raised after SQLite remains locked or busy after bounded retries."""


@dataclass(frozen=True, slots=True)
class BatchAddResult:
    """Outcome of one atomic bounded email batch."""

    imported: int
    skipped: int


@dataclass(frozen=True, slots=True)
class RankedEmailRecord:
    """One FTS result with its raw score and stable one-based rank."""

    record: EmailRecord
    fts_score: float
    fts_rank: int


def is_database_busy_error(error: BaseException) -> bool:
    """Return whether an exception represents SQLite lock contention."""
    message = str(error).casefold()
    return "database is locked" in message or "database is busy" in message


def retry_on_database_busy(
    operation: Callable[[], T],
    *,
    max_retries: int = DEFAULT_MAX_LOCK_RETRIES,
    base_delay_seconds: float = DEFAULT_RETRY_BASE_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Retry one idempotent operation after transient SQLite lock failures."""
    if max_retries < 0:
        raise ValueError("max_retries must not be negative")
    if base_delay_seconds < 0:
        raise ValueError("base_delay_seconds must not be negative")

    for retry_number in range(max_retries + 1):
        try:
            return operation()
        except sqlite3.OperationalError as error:
            if not is_database_busy_error(error):
                raise
            if retry_number == max_retries:
                raise DatabaseBusyError(
                    "SQLite remained temporarily busy after bounded retries."
                ) from error
            sleep(base_delay_seconds * (2**retry_number))
    raise AssertionError("retry loop must return or raise")


class SQLiteEmailStore:
    """Persist and search email records in SQLite."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        read_only: bool = False,
        connection_timeout_seconds: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        max_lock_retries: int = DEFAULT_MAX_LOCK_RETRIES,
        retry_base_delay_seconds: float = DEFAULT_RETRY_BASE_DELAY_SECONDS,
    ) -> None:
        if connection_timeout_seconds < 0:
            raise ValueError("connection_timeout_seconds must not be negative")
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must not be negative")
        if max_lock_retries < 0:
            raise ValueError("max_lock_retries must not be negative")
        if retry_base_delay_seconds < 0:
            raise ValueError("retry_base_delay_seconds must not be negative")
        self._database_path = Path(database_path)
        self._read_only = read_only
        self._connection_timeout_seconds = connection_timeout_seconds
        self._busy_timeout_ms = busy_timeout_ms
        self._max_lock_retries = max_lock_retries
        self._retry_base_delay_seconds = retry_base_delay_seconds

    def _open_connection(self) -> sqlite3.Connection:
        if self._read_only:
            database_uri = self._database_path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(
                database_uri,
                uri=True,
                timeout=self._connection_timeout_seconds,
            )
        else:
            connection = sqlite3.connect(
                self._database_path,
                timeout=self._connection_timeout_seconds,
            )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        return connection

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._open_connection()
        try:
            yield connection
            if not self._read_only:
                connection.commit()
        except sqlite3.OperationalError as error:
            if is_database_busy_error(error):
                raise DatabaseBusyError(
                    "The local email database is temporarily busy."
                ) from error
            raise
        finally:
            connection.close()

    def initialise(self) -> None:
        """Create the database schema without changing its journal mode."""
        if self._read_only:
            raise sqlite3.OperationalError("store is read-only")
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    @staticmethod
    def _record_values(record: EmailRecord) -> tuple[object, ...]:
        return (
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
        )

    def _add_many_once(self, records: Sequence[EmailRecord]) -> BatchAddResult:
        connection = self._open_connection()
        imported = 0
        try:
            connection.execute("BEGIN IMMEDIATE")
            for record in records:
                cursor = connection.execute(_INSERT_EMAIL, self._record_values(record))
                imported += int(cursor.rowcount == 1)
            connection.commit()
        except BaseException:
            with suppress(sqlite3.Error):
                connection.rollback()
            raise
        finally:
            connection.close()
        return BatchAddResult(imported=imported, skipped=len(records) - imported)

    def add_many(self, records: Sequence[EmailRecord]) -> BatchAddResult:
        """Atomically insert one bounded batch with duplicate-safe lock retries."""
        if self._read_only:
            raise sqlite3.OperationalError("store is read-only")
        if not records:
            return BatchAddResult(imported=0, skipped=0)
        batch = tuple(records)
        return retry_on_database_busy(
            lambda: self._add_many_once(batch),
            max_retries=self._max_lock_retries,
            base_delay_seconds=self._retry_base_delay_seconds,
        )

    def add(self, record: EmailRecord) -> bool:
        """Insert a record; return False when its source key already exists."""
        return self.add_many((record,)).imported == 1

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

    def folder_counts(self) -> tuple[tuple[str, int], ...]:
        """Return deterministic per-folder record counts without loading emails."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT folder_path, COUNT(*) AS total
                FROM emails
                GROUP BY folder_path
                ORDER BY folder_path
                """
            ).fetchall()
        return tuple((str(row["folder_path"]), int(row["total"])) for row in rows)

    def search(self, query: str, *, limit: int = 20) -> list[EmailRecord]:
        """Search subject, sender and body using FTS5."""
        return [item.record for item in self.search_ranked(query, limit=limit)]

    def search_ranked(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[RankedEmailRecord]:
        """Search FTS5 and retain raw BM25 scores for downstream reranking."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT emails.*, bm25(emails_fts) AS fts_score
                FROM emails_fts
                JOIN emails ON emails.id = emails_fts.rowid
                WHERE emails_fts MATCH ?
                ORDER BY fts_score, emails.id
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [
            RankedEmailRecord(
                record=_row_to_record(row),
                fts_score=float(row["fts_score"]),
                fts_rank=rank,
            )
            for rank, row in enumerate(rows, start=1)
        ]


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
