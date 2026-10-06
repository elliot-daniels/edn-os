"""Metadata-only durable history for bounded Operations import attempts."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ImportOutcome:
    run_id: str
    source: str
    source_account: str
    window_start: str
    window_end: str
    started_at: str
    finished_at: str | None
    state: str
    inserted: int
    duplicates: int
    failed: int
    pages: int
    reason: str | None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str):
            raise ValueError("Invalid import run identity")
        try:
            UUID(self.run_id)
        except (ValueError, AttributeError) as error:
            raise ValueError("Invalid import run identity") from error
        if (
            self.source != "outlook"
            or not isinstance(self.source_account, str)
            or not self.source_account.strip()
            or self.source_account != self.source_account.strip()
        ):
            raise ValueError("Invalid import source identity")
        times = []
        for value in (self.window_start, self.window_end, self.started_at):
            if not isinstance(value, str):
                raise ValueError("Invalid import timestamp")
            timestamp = datetime.fromisoformat(value)
            if timestamp.utcoffset() is None:
                raise ValueError("Import timestamps must be aware")
            times.append(timestamp)
        if not timedelta(0) <= times[1] - times[0] <= timedelta(days=31):
            raise ValueError("Invalid import window")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported import outcome schema")
        if self.state not in {"in_progress", "complete", "partial", "failed"}:
            raise ValueError("Invalid import outcome state")
        if self.reason not in {None, "malformed_records", "page_limit", "import_error"}:
            raise ValueError("Invalid import outcome reason")
        if any(
            type(value) is not int or value < 0
            for value in (self.inserted, self.duplicates, self.failed, self.pages)
        ):
            raise ValueError("Invalid import outcome counts")
        if self.pages > 100 or self.inserted + self.duplicates + self.failed > 5000:
            raise ValueError("Import outcome exceeds intake bounds")
        if self.state == "in_progress":
            if self.finished_at is not None or self.reason is not None:
                raise ValueError("In-progress import cannot be finalized")
        else:
            if (
                not isinstance(self.finished_at, str)
                or datetime.fromisoformat(self.finished_at).utcoffset() is None
            ):
                raise ValueError("Finalized import needs an aware finish timestamp")
            if self.state == "complete" and (
                self.failed != 0 or self.reason is not None or self.pages == 0
            ):
                raise ValueError("Complete import cannot contain failures")
            if self.state in {"partial", "failed"} and self.reason is None:
                raise ValueError("Incomplete import needs a fixed reason")
            if self.state == "failed" and (
                self.reason != "import_error"
                or any((self.inserted, self.duplicates, self.failed, self.pages))
            ):
                raise ValueError("Failed import cannot contain committed progress")
            if self.state == "partial" and (
                (self.reason == "malformed_records" and self.failed == 0)
                or (self.reason == "page_limit" and self.pages == 0)
                or (
                    self.reason == "import_error"
                    and not any(
                        (self.inserted, self.duplicates, self.failed, self.pages)
                    )
                )
            ):
                raise ValueError("Partial import must explain recorded progress")


class ImportOutcomeStore:
    """Separate additive table; never creates a missing Event database on reads."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only

    def _connect(self) -> sqlite3.Connection:
        mode = "ro" if self.read_only else "rw"
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode={mode}", uri=True
        )
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError("Unsupported Operations Event schema")
            table = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='operations_import_outcomes'"
            ).fetchone()
            if table is not None:
                expected = [("run_id", "TEXT", 0, 1)] + [
                    (name, kind, nullable, 0)
                    for name, kind, nullable in (
                        ("source", "TEXT", 1),
                        ("source_account", "TEXT", 1),
                        ("window_start", "TEXT", 1),
                        ("window_end", "TEXT", 1),
                        ("started_at", "TEXT", 1),
                        ("finished_at", "TEXT", 0),
                        ("state", "TEXT", 1),
                        ("inserted", "INTEGER", 1),
                        ("duplicates", "INTEGER", 1),
                        ("failed", "INTEGER", 1),
                        ("pages", "INTEGER", 1),
                        ("reason", "TEXT", 0),
                        ("schema_version", "INTEGER", 1),
                    )
                ]
                columns = connection.execute(
                    "PRAGMA table_info(operations_import_outcomes)"
                ).fetchall()
                observed = [(row[1], row[2], row[3], row[5]) for row in columns]
                if (
                    observed != expected
                    or any(row[4] is not None for row in columns)
                    or re.search(
                        r"CHECK\s*\(\s*schema_version\s*=\s*1\s*\)",
                        table[0],
                        re.IGNORECASE,
                    )
                    is None
                ):
                    raise ValueError("Unsupported import outcome table schema")
            if (
                table is not None
                and connection.execute(
                    "SELECT 1 FROM operations_import_outcomes "
                    "WHERE schema_version <> 1 LIMIT 1"
                ).fetchone()
                is not None
            ):
                raise ValueError("Unsupported import outcome schema")
        except Exception:
            connection.close()
            raise
        return connection

    def validate(self) -> None:
        """Read-only compatibility preflight for an existing selected database."""
        with self._connect():
            pass

    def initialise(self) -> None:
        if self.read_only:
            raise ValueError("Read-only outcome store cannot initialise")
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS operations_import_outcomes (
                run_id TEXT PRIMARY KEY, source TEXT NOT NULL,
                source_account TEXT NOT NULL, window_start TEXT NOT NULL,
                window_end TEXT NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, state TEXT NOT NULL,
                inserted INTEGER NOT NULL, duplicates INTEGER NOT NULL,
                failed INTEGER NOT NULL, pages INTEGER NOT NULL, reason TEXT,
                schema_version INTEGER NOT NULL CHECK(schema_version=1)
            )""")

    def begin(self, account: str, start: datetime, end: datetime) -> str:
        if self.read_only:
            raise ValueError("Read-only outcome store cannot begin imports")
        run_id = str(uuid4())
        started_at = datetime.now(UTC).isoformat()
        ImportOutcome(
            run_id,
            "outlook",
            account.casefold(),
            start.isoformat(),
            end.isoformat(),
            started_at,
            None,
            "in_progress",
            0,
            0,
            0,
            0,
            None,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO operations_import_outcomes VALUES "
                "(?, 'outlook', ?, ?, ?, ?, NULL, 'in_progress', 0, 0, 0, 0, NULL, 1)",
                (
                    run_id,
                    account.casefold(),
                    start.isoformat(),
                    end.isoformat(),
                    started_at,
                ),
            )
        return run_id

    def update(
        self,
        run_id: str,
        *,
        inserted: int,
        duplicates: int,
        failed: int,
        pages: int,
        state: str = "in_progress",
        reason: str | None = None,
    ) -> None:
        if self.read_only:
            raise ValueError("Read-only outcome store cannot update imports")
        if state not in {"in_progress", "complete", "partial", "failed"}:
            raise ValueError("Invalid import outcome state")
        if reason not in {None, "malformed_records", "page_limit", "import_error"}:
            raise ValueError("Invalid import outcome reason")
        if any(
            type(value) is not int or value < 0
            for value in (inserted, duplicates, failed, pages)
        ):
            raise ValueError("Import counts cannot be negative")
        finished = None if state == "in_progress" else datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM operations_import_outcomes WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Import outcome is missing")
            replace(
                ImportOutcome(*row),
                inserted=inserted,
                duplicates=duplicates,
                failed=failed,
                pages=pages,
                state=state,
                reason=reason,
                finished_at=finished,
            )
            cursor = connection.execute(
                "UPDATE operations_import_outcomes SET inserted=?, duplicates=?, "
                "failed=?, pages=?, state=?, reason=?, finished_at=? "
                "WHERE run_id=? AND state='in_progress'",
                (inserted, duplicates, failed, pages, state, reason, finished, run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Import outcome is missing or already finalized")

    def latest(
        self, *, account: str | None = None, limit: int = 20
    ) -> tuple[ImportOutcome, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Outcome list limit must be between 1 and 100")
        if account is not None and (
            not isinstance(account, str) or not account.strip()
        ):
            raise ValueError("Outcome account must be nonblank")
        with self._connect() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='operations_import_outcomes'"
            ).fetchone()
            if table is None:
                return ()
            where = " WHERE source_account=?" if account is not None else ""
            parameters: tuple[str | int, ...] = (
                (account.casefold(), limit) if account is not None else (limit,)
            )
            rows = connection.execute(
                "SELECT * FROM operations_import_outcomes"
                + where
                + " ORDER BY started_at DESC, run_id DESC LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(ImportOutcome(*row) for row in rows)
