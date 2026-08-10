"""Dedicated SQLite persistence for jobs, checkpoints, attempts, and audit."""

# ruff: noqa: E501 -- SQL statements remain readable as complete clauses.

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from edn.connectors import Checkpoint
from edn.jobs.models import AuditEvent, Job, JobAttempt, JobStatus

SCHEMA_VERSION = 1
DEFAULT_CONNECTION_TIMEOUT_SECONDS = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 30_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    connector_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    next_retry_at TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_claimable
ON jobs(status, next_retry_at, created_at, job_id);
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_attempts (
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    attempt_number INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    outcome TEXT,
    error_code TEXT,
    PRIMARY KEY(job_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    job_id TEXT NOT NULL REFERENCES jobs(job_id),
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_job_sequence ON audit_events(job_id, sequence);
CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
"""


@dataclass(frozen=True, slots=True)
class JobMetrics:
    status_counts: tuple[tuple[JobStatus, int], ...]
    average_duration_seconds: float | None
    retry_count: int
    checkpoint_count: int
    failure_reason_counts: tuple[tuple[str, int], ...]


class JobStore:
    def __init__(
        self,
        database_path: str | Path,
        *,
        read_only: bool = False,
        connection_timeout_seconds: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if connection_timeout_seconds < 0 or busy_timeout_ms < 0:
            raise ValueError("SQLite timeout values must not be negative")
        self._path = Path(database_path)
        self._read_only = read_only
        self._connection_timeout_seconds = connection_timeout_seconds
        self._busy_timeout_ms = busy_timeout_ms

    def _open(self) -> sqlite3.Connection:
        if self._read_only:
            uri = self._path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(
                uri, uri=True, timeout=self._connection_timeout_seconds
            )
        else:
            connection = sqlite3.connect(
                self._path, timeout=self._connection_timeout_seconds
            )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()
        try:
            yield connection
            if not self._read_only:
                connection.commit()
        except BaseException:
            if not self._read_only:
                with suppress(sqlite3.Error):
                    connection.rollback()
            raise
        finally:
            connection.close()

    def initialise(self) -> None:
        if self._read_only:
            raise sqlite3.OperationalError("store is read-only")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            metadata_exists = connection.execute(
                """SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_metadata'"""
            ).fetchone()
            if metadata_exists is not None:
                existing = connection.execute(
                    "SELECT version FROM schema_metadata WHERE component = 'jobs'"
                ).fetchone()
                if existing is None or int(existing["version"]) != SCHEMA_VERSION:
                    raise RuntimeError(
                        "unsupported Intelligence Core job schema version"
                    )
            connection.executescript(_SCHEMA)
            row = connection.execute(
                "SELECT version FROM schema_metadata WHERE component = 'jobs'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_metadata(component, version) VALUES ('jobs', ?)",
                    (SCHEMA_VERSION,),
                )

    def check_schema(self) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version FROM schema_metadata WHERE component = 'jobs'"
            ).fetchone()
        if row is None or int(row["version"]) != SCHEMA_VERSION:
            raise RuntimeError("unsupported or missing Intelligence Core job schema")

    def create(self, job: Job, event: AuditEvent) -> None:
        if event.job_id != job.job_id or event.event_type != "job_created":
            raise ValueError("job creation requires its matching job_created event")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_job(connection, job)
            self._insert_event(connection, event)

    def get(self, job_id: str) -> Job | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else _decode_job(str(row["payload_json"]))

    def list(
        self,
        *,
        statuses: frozenset[JobStatus] | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> tuple[Job, ...]:
        if limit < 1:
            raise ValueError("limit must be at least one")
        clauses: list[str] = []
        parameters: list[object] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(sorted(status.value for status in statuses))
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            parameters.append(tenant_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM jobs{where} ORDER BY created_at, job_id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(_decode_job(str(row["payload_json"])) for row in rows)

    def claimable(self, *, now: datetime, limit: int = 100) -> tuple[Job, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM jobs
                WHERE status = ? OR (status = ? AND next_retry_at <= ?)
                ORDER BY created_at, job_id LIMIT ?
                """,
                (
                    JobStatus.READY.value,
                    JobStatus.RETRY_WAIT.value,
                    _time(now),
                    limit,
                ),
            ).fetchall()
        return tuple(_decode_job(str(row["payload_json"])) for row in rows)

    def claim(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        event: AuditEvent,
    ) -> Job | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json, status, next_retry_at FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            status = JobStatus(row["status"])
            retry_due = row["next_retry_at"] is not None and str(
                row["next_retry_at"]
            ) <= _time(now)
            if status is not JobStatus.READY and not (
                status is JobStatus.RETRY_WAIT and retry_due
            ):
                return None
            current = _decode_job(str(row["payload_json"]))
            claimed = replace(
                current,
                status=JobStatus.RUNNING,
                attempt_count=current.attempt_count + 1,
                started_at=current.started_at or now,
                updated_at=now,
                next_retry_at=None,
                error=None,
            )
            self._update_job(connection, claimed)
            connection.execute(
                """INSERT INTO job_attempts(
                    job_id, attempt_number, worker_id, started_at
                ) VALUES (?, ?, ?, ?)""",
                (job_id, claimed.attempt_count, worker_id, _time(now)),
            )
            self._insert_event(connection, event)
            return claimed

    def transition(
        self,
        job: Job,
        *,
        expected_statuses: frozenset[JobStatus],
        event: AuditEvent,
        attempt_outcome: str | None = None,
        attempt_error_code: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job.job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job.job_id)
            if JobStatus(row["status"]) not in expected_statuses:
                raise RuntimeError("job status changed concurrently")
            self._update_job(connection, job)
            if attempt_outcome is not None:
                connection.execute(
                    """UPDATE job_attempts SET completed_at = ?, outcome = ?, error_code = ?
                    WHERE job_id = ? AND attempt_number = ?""",
                    (
                        _time(job.updated_at),
                        attempt_outcome,
                        attempt_error_code,
                        job.job_id,
                        job.attempt_count,
                    ),
                )
            self._insert_event(connection, event)

    def save_checkpoint(
        self,
        job: Job,
        checkpoint: Checkpoint,
        *,
        event: AuditEvent,
    ) -> None:
        if checkpoint.checkpoint_id != job.checkpoint_id:
            raise ValueError("job checkpoint reference does not match checkpoint")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job.job_id,)
            ).fetchone()
            if row is None or JobStatus(row["status"]) is not JobStatus.RUNNING:
                raise RuntimeError("only a running job may save a checkpoint")
            connection.execute(
                """INSERT INTO checkpoints(checkpoint_id, job_id, created_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    checkpoint_id = excluded.checkpoint_id,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json""",
                (
                    checkpoint.checkpoint_id,
                    job.job_id,
                    _time(checkpoint.created_at),
                    checkpoint.to_json(),
                ),
            )
            self._update_job(connection, job)
            connection.execute(
                """UPDATE job_attempts SET completed_at = ?, outcome = 'checkpointed'
                WHERE job_id = ? AND attempt_number = ?""",
                (_time(job.updated_at), job.job_id, job.attempt_count),
            )
            self._insert_event(connection, event)

    def checkpoint(self, job_id: str) -> Checkpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM checkpoints WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row["payload_json"]))
        if not isinstance(value, dict):
            raise ValueError("stored checkpoint is invalid")
        return Checkpoint.from_dict(value)

    def history(self, job_id: str) -> tuple[AuditEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM audit_events WHERE job_id = ? ORDER BY sequence",
                (job_id,),
            ).fetchall()
        return tuple(_decode_event(str(row["payload_json"])) for row in rows)

    def append_event(self, event: AuditEvent) -> None:
        """Append one content-safe event; database triggers forbid later mutation."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_event(connection, event)

    def attempts(self, job_id: str) -> tuple[JobAttempt, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM job_attempts WHERE job_id = ? ORDER BY attempt_number",
                (job_id,),
            ).fetchall()
        return tuple(
            JobAttempt(
                str(row["job_id"]),
                int(row["attempt_number"]),
                str(row["worker_id"]),
                datetime.fromisoformat(str(row["started_at"])),
                None
                if row["completed_at"] is None
                else datetime.fromisoformat(str(row["completed_at"])),
                None if row["outcome"] is None else str(row["outcome"]),
                None if row["error_code"] is None else str(row["error_code"]),
            )
            for row in rows
        )

    def metrics(self) -> JobMetrics:
        with self._connect() as connection:
            status_rows = connection.execute(
                "SELECT status, COUNT(*) total FROM jobs GROUP BY status ORDER BY status"
            ).fetchall()
            duration_row = connection.execute(
                """SELECT AVG((julianday(json_extract(payload_json, '$.completed_at')) -
                    julianday(json_extract(payload_json, '$.started_at'))) * 86400.0) average
                FROM jobs WHERE status IN (?, ?)""",
                (JobStatus.COMPLETED.value, JobStatus.COMPLETED_WITH_WARNINGS.value),
            ).fetchone()
            retry_row = connection.execute(
                "SELECT COUNT(*) total FROM audit_events WHERE event_type = 'retry_scheduled'"
            ).fetchone()
            checkpoint_row = connection.execute(
                "SELECT COUNT(*) total FROM audit_events WHERE event_type = 'checkpoint_saved'"
            ).fetchone()
            failure_rows = connection.execute(
                """SELECT json_extract(payload_json, '$.reason_code') reason, COUNT(*) total
                FROM audit_events WHERE event_type = 'job_failed'
                GROUP BY reason ORDER BY reason"""
            ).fetchall()
        average = (
            None
            if duration_row is None or duration_row["average"] is None
            else float(duration_row["average"])
        )
        return JobMetrics(
            tuple((JobStatus(row["status"]), int(row["total"])) for row in status_rows),
            average,
            0 if retry_row is None else int(retry_row["total"]),
            0 if checkpoint_row is None else int(checkpoint_row["total"]),
            tuple((str(row["reason"]), int(row["total"])) for row in failure_rows),
        )

    @staticmethod
    def _insert_job(connection: sqlite3.Connection, job: Job) -> None:
        connection.execute(
            """INSERT INTO jobs(
                job_id, status, tenant_id, connector_id, capability_id, operation,
                created_at, updated_at, next_retry_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            _job_values(job),
        )

    @staticmethod
    def _update_job(connection: sqlite3.Connection, job: Job) -> None:
        values = _job_values(job)
        connection.execute(
            """UPDATE jobs SET status = ?, tenant_id = ?, connector_id = ?,
                capability_id = ?, operation = ?, created_at = ?, updated_at = ?,
                next_retry_at = ?, payload_json = ? WHERE job_id = ?""",
            (*values[1:], values[0]),
        )

    @staticmethod
    def _insert_event(connection: sqlite3.Connection, event: AuditEvent) -> None:
        connection.execute(
            """INSERT INTO audit_events(
                event_id, job_id, event_type, timestamp, payload_json
            ) VALUES (?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.job_id,
                event.event_type,
                _time(event.timestamp),
                json.dumps(
                    event.to_dict(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            ),
        )


def _job_values(job: Job) -> tuple[object, ...]:
    return (
        job.job_id,
        job.status.value,
        job.principal.tenant_id,
        job.connector_id,
        job.capability_id,
        job.operation,
        _time(job.created_at),
        _time(job.updated_at),
        None if job.next_retry_at is None else _time(job.next_retry_at),
        job.to_json(),
    )


def _time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.isoformat()


def _decode_job(payload: str) -> Job:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("stored job is invalid")
    return Job.from_dict(value)


def _decode_event(payload: str) -> AuditEvent:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("stored audit event is invalid")
    return AuditEvent.from_dict(value)
