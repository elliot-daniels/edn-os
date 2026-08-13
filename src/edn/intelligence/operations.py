"""Local-only Daily Intelligence scheduling, run lifecycle, and status."""

# ruff: noqa: E501 -- SQL clauses and compact status strings remain readable.

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from edn.development.models import AuditEvent
from edn.intelligence.models import DailyIntelligenceBrief

EDN_TIMEZONE = "Australia/Adelaide"
_ZONE = ZoneInfo(EDN_TIMEZONE)
_SCHEMA_VERSION = 1


class RunStatus(StrEnum):
    DUE = "due"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_GAPS = "completed_with_gaps"
    FAILED = "failed"
    MISSED = "missed"


class RunFailureCode(StrEnum):
    AUTHORITY_DENIED = "authority_denied"
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    BRIEF_ASSEMBLY_FAILED = "brief_assembly_failed"
    SCHEDULER_INTERRUPTED = "scheduler_interrupted"
    BACKUP_INTEGRITY_FAILED = "backup_integrity_failed"


@dataclass(frozen=True, slots=True)
class DailySchedule:
    schedule_id: str = "daily-intelligence"
    cadence: str = "daily"
    local_time: time = time(8, 0)
    timezone: str = EDN_TIMEZONE
    next_expected_run: datetime | None = None
    last_attempted_run: datetime | None = None
    last_successful_run: datetime | None = None

    def __post_init__(self) -> None:
        if not self.schedule_id or self.cadence != "daily":
            raise ValueError("Daily Intelligence requires a daily schedule identity")
        if self.timezone != EDN_TIMEZONE:
            raise ValueError(f"schedule timezone must be {EDN_TIMEZONE}")
        for value in (
            self.next_expected_run,
            self.last_attempted_run,
            self.last_successful_run,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("schedule timestamps must be timezone-aware")

    def initialise(self, *, now: datetime) -> DailySchedule:
        _aware(now)
        if self.next_expected_run is not None:
            return self
        local_now = now.astimezone(_ZONE)
        candidate = _at_local(local_now.date(), self.local_time)
        if candidate <= local_now:
            candidate = _at_local(local_now.date() + timedelta(days=1), self.local_time)
        return replace(self, next_expected_run=candidate)

    def advance(self, *, after: datetime) -> DailySchedule:
        _aware(after)
        local_after = after.astimezone(_ZONE)
        candidate = _at_local(local_after.date() + timedelta(days=1), self.local_time)
        return replace(self, next_expected_run=candidate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "cadence": self.cadence,
            "local_time": self.local_time.isoformat(),
            "timezone": self.timezone,
            "next_expected_run": _format(self.next_expected_run),
            "last_attempted_run": _format(self.last_attempted_run),
            "last_successful_run": _format(self.last_successful_run),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DailySchedule:
        return cls(
            str(value["schedule_id"]),
            str(value["cadence"]),
            time.fromisoformat(str(value["local_time"])),
            str(value["timezone"]),
            _parse(value.get("next_expected_run")),
            _parse(value.get("last_attempted_run")),
            _parse(value.get("last_successful_run")),
        )


@dataclass(frozen=True, slots=True)
class DailyRun:
    run_id: str
    schedule_id: str
    scheduled_for: datetime
    attempt: int
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_ref: str | None = None
    evidence_gap_count: int = 0
    failure_code: str | None = None
    failure_detail: str | None = None
    retry_safe: bool = False
    missed_reason: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.scheduled_for,
            self.created_at,
            self.started_at,
            self.completed_at,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("run timestamps must be timezone-aware")
        if self.attempt < 1 or self.evidence_gap_count < 0:
            raise ValueError("run attempt and gap count must be positive/nonnegative")
        if self.status in {
            RunStatus.COMPLETED,
            RunStatus.COMPLETED_WITH_GAPS,
        } and (self.completed_at is None or self.result_ref is None):
            raise ValueError("completed run requires result and completion time")
        if self.status is RunStatus.FAILED and not self.failure_code:
            raise ValueError("failed run requires a deterministic failure code")

    @staticmethod
    def deterministic_id(schedule_id: str, scheduled_for: datetime) -> str:
        key = f"{schedule_id}:{scheduled_for.astimezone(UTC).isoformat()}"
        return "daily-run-" + hashlib.sha256(key.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "schedule_id": self.schedule_id,
            "scheduled_for": self.scheduled_for.isoformat(),
            "attempt": self.attempt,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": _format(self.started_at),
            "completed_at": _format(self.completed_at),
            "result_ref": self.result_ref,
            "evidence_gap_count": self.evidence_gap_count,
            "failure_code": self.failure_code,
            "failure_detail": self.failure_detail,
            "retry_safe": self.retry_safe,
            "missed_reason": self.missed_reason,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DailyRun:
        return cls(
            str(value["run_id"]),
            str(value["schedule_id"]),
            datetime.fromisoformat(str(value["scheduled_for"])),
            int(value["attempt"]),
            RunStatus(str(value["status"])),
            datetime.fromisoformat(str(value["created_at"])),
            _parse(value.get("started_at")),
            _parse(value.get("completed_at")),
            None if value.get("result_ref") is None else str(value["result_ref"]),
            int(value.get("evidence_gap_count", 0)),
            None if value.get("failure_code") is None else str(value["failure_code"]),
            None
            if value.get("failure_detail") is None
            else str(value["failure_detail"]),
            bool(value.get("retry_safe", False)),
            None if value.get("missed_reason") is None else str(value["missed_reason"]),
        )


@dataclass(frozen=True, slots=True)
class DailyOperationalStatus:
    schedule_id: str
    health: str
    last_successful_run: datetime | None
    latest_attempt: DailyRun | None
    next_run: datetime | None
    recovery_required: bool
    scheduler_healthy: bool
    run_due: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "health": self.health,
            "last_successful_run": _format(self.last_successful_run),
            "latest_attempt": None
            if self.latest_attempt is None
            else self.latest_attempt.to_dict(),
            "next_run": _format(self.next_run),
            "recovery_required": self.recovery_required,
            "scheduler_healthy": self.scheduler_healthy,
            "run_due": self.run_due,
        }

    def render(self) -> str:
        latest = self.latest_attempt
        today = (
            "Due"
            if self.run_due and not self.recovery_required
            else "Complete"
            if latest is not None
            and latest.status in {RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_GAPS}
            else "Failed"
            if latest is not None and latest.status is RunStatus.FAILED
            else "Missed"
            if latest is not None and latest.status is RunStatus.MISSED
            else "Due"
            if latest is not None and latest.status is RunStatus.DUE
            else "Not run"
        )
        reason = ""
        if latest is not None and latest.failure_code:
            reason = f"\nReason: {latest.failure_code}"
        return (
            f"Daily Intelligence\nStatus: {self.health}\n"
            f"Last success: {_display(self.last_successful_run)}\n"
            f"Latest attempt: {today}\n"
            f"Next run: {_display(self.next_run)}"
            f"{reason}\nRecovery: {'required' if self.recovery_required else 'not required'}"
        )


@dataclass(frozen=True, slots=True)
class BriefRunResult:
    result_ref: str
    evidence_gap_count: int = 0

    @classmethod
    def from_brief(
        cls, brief: DailyIntelligenceBrief, result_ref: str
    ) -> BriefRunResult:
        gaps = sum(1 for item in brief.items if item.kind.value == "unknown")
        return cls(result_ref, gaps)


class DailyBriefRunner(Protocol):
    def __call__(self) -> BriefRunResult: ...


class DailyOperationsStore:
    """Small SQLite store for schedule/run state and content-free audit events."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialise(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_ops_schema (
                    component TEXT PRIMARY KEY, version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_schedules (
                    schedule_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_runs (
                    run_id TEXT PRIMARY KEY, scheduled_for TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL, payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_run_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS daily_audit_no_update
                BEFORE UPDATE ON daily_run_audit BEGIN SELECT RAISE(ABORT, 'daily audit is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS daily_audit_no_delete
                BEFORE DELETE ON daily_run_audit BEGIN SELECT RAISE(ABORT, 'daily audit is append-only'); END;
                """
            )
            row = connection.execute(
                "SELECT version FROM daily_ops_schema WHERE component='daily-operations'"
            ).fetchone()
            if row is not None and int(row["version"]) != _SCHEMA_VERSION:
                raise RuntimeError("unsupported Daily Intelligence operations schema")
            if row is None:
                connection.execute(
                    "INSERT INTO daily_ops_schema(component, version) VALUES (?, ?)",
                    ("daily-operations", _SCHEMA_VERSION),
                )

    def check_schema(self) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT version FROM daily_ops_schema WHERE component='daily-operations'"
            ).fetchone()
        if row is None or int(row["version"]) != _SCHEMA_VERSION:
            raise RuntimeError(
                "unsupported or missing Daily Intelligence operations schema"
            )

    def save_schedule(self, schedule: DailySchedule) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO daily_schedules(schedule_id,payload_json) VALUES (?,?) "
                "ON CONFLICT(schedule_id) DO UPDATE SET payload_json=excluded.payload_json",
                (schedule.schedule_id, json.dumps(schedule.to_dict(), sort_keys=True)),
            )

    def get_schedule(self, schedule_id: str) -> DailySchedule | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_schedules WHERE schedule_id=?",
                (schedule_id,),
            ).fetchone()
        return (
            None
            if row is None
            else DailySchedule.from_dict(json.loads(row["payload_json"]))
        )

    def save_run(self, run: DailyRun) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO daily_runs(run_id,scheduled_for,status,payload_json) VALUES (?,?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status,payload_json=excluded.payload_json",
                (
                    run.run_id,
                    run.scheduled_for.isoformat(),
                    run.status.value,
                    json.dumps(run.to_dict(), sort_keys=True),
                ),
            )

    def get_run(self, run_id: str) -> DailyRun | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return (
            None if row is None else DailyRun.from_dict(json.loads(row["payload_json"]))
        )

    def get_run_for_schedule_time(self, scheduled_for: datetime) -> DailyRun | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_runs WHERE scheduled_for=?",
                (scheduled_for.isoformat(),),
            ).fetchone()
        return (
            None if row is None else DailyRun.from_dict(json.loads(row["payload_json"]))
        )

    def latest_run(self) -> DailyRun | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM daily_runs ORDER BY scheduled_for DESC LIMIT 1"
            ).fetchone()
        return (
            None if row is None else DailyRun.from_dict(json.loads(row["payload_json"]))
        )

    def append_audit(self, event: AuditEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO daily_run_audit(event_id,run_id,event_type,timestamp,payload_json) VALUES (?,?,?,?,?)",
                (
                    event.event_id,
                    event.task_id or event.event_id,
                    event.event_type,
                    event.timestamp.isoformat(),
                    json.dumps(event.to_dict(), sort_keys=True),
                ),
            )

    def history(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM daily_run_audit WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return tuple(json.loads(row["payload_json"]) for row in rows)


class DailyIntelligenceScheduler:
    """Deterministic local scheduler; it never installs or starts a service."""

    def __init__(
        self, store: DailyOperationsStore, schedule: DailySchedule | None = None
    ) -> None:
        self.store = store
        self.schedule = schedule or DailySchedule()

    def initialise(self, *, now: datetime) -> DailySchedule:
        self.store.initialise()
        schedule = self.store.get_schedule(self.schedule.schedule_id) or self.schedule
        schedule = schedule.initialise(now=now)
        self.store.save_schedule(schedule)
        return schedule

    def tick(self, *, now: datetime, runner: DailyBriefRunner) -> DailyRun | None:
        schedule = self.initialise(now=now)
        assert schedule.next_expected_run is not None
        if now < schedule.next_expected_run:
            latest = self.store.latest_run()
            if (
                latest is not None
                and latest.schedule_id == schedule.schedule_id
                and latest.completed_at is not None
                and latest.completed_at <= now
            ):
                self._event(
                    latest,
                    "duplicate_suppressed",
                    "next_cadence_not_due",
                    "suppressed",
                    now=now,
                )
            return None
        scheduled_for = schedule.next_expected_run
        existing = self.store.get_run_for_schedule_time(scheduled_for)
        if existing is not None:
            self._event(
                existing,
                "duplicate_suppressed",
                "logical_run_already_recorded",
                "suppressed",
                now=now,
            )
            return existing
        run = DailyRun(
            DailyRun.deterministic_id(schedule.schedule_id, scheduled_for),
            schedule.schedule_id,
            scheduled_for,
            1,
            RunStatus.RUNNING,
            now,
            started_at=now,
        )
        try:
            self.store.save_run(run)
        except sqlite3.IntegrityError:
            existing = self.store.get_run_for_schedule_time(scheduled_for)
            if existing is not None:
                self._event(
                    existing,
                    "duplicate_suppressed",
                    "logical_run_already_recorded",
                    "suppressed",
                    now=now,
                )
                return existing
            raise
        self._event(run, "run_started", "schedule_due", "running", now=now)
        self.store.save_schedule(replace(schedule, last_attempted_run=now))
        try:
            result = runner()
        except PermissionError:
            return self._fail(
                run,
                now,
                RunFailureCode.AUTHORITY_DENIED,
                "daily brief authority denied",
            )
        except Exception:
            return self._fail(
                run,
                now,
                RunFailureCode.BRIEF_ASSEMBLY_FAILED,
                "daily brief assembly failed",
            )
        status = (
            RunStatus.COMPLETED_WITH_GAPS
            if result.evidence_gap_count
            else RunStatus.COMPLETED
        )
        completed = replace(
            run,
            status=status,
            completed_at=now,
            result_ref=result.result_ref,
            evidence_gap_count=result.evidence_gap_count,
        )
        self.store.save_run(completed)
        self._event(
            completed,
            "run_completed",
            "completed_with_gaps" if result.evidence_gap_count else "completed",
            status.value,
            now=now,
        )
        self.store.save_schedule(
            replace(schedule, last_attempted_run=now, last_successful_run=now).advance(
                after=scheduled_for
            )
        )
        return completed

    def retry(
        self, run_id: str, *, now: datetime, runner: DailyBriefRunner
    ) -> DailyRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status is not RunStatus.FAILED or not run.retry_safe:
            raise ValueError("only failed runs marked retry-safe may be retried")
        retrying = replace(
            run,
            status=RunStatus.RUNNING,
            attempt=run.attempt + 1,
            started_at=now,
            completed_at=None,
            failure_code=None,
            failure_detail=None,
        )
        self.store.save_run(retrying)
        self._event(retrying, "run_retry_started", "safe_retry", "running", now=now)
        schedule = self.store.get_schedule(run.schedule_id)
        if schedule is not None:
            self.store.save_schedule(replace(schedule, last_attempted_run=now))
        try:
            result = runner()
        except Exception:
            return self._fail(
                retrying,
                now,
                RunFailureCode.BRIEF_ASSEMBLY_FAILED,
                "daily brief retry failed",
            )
        status = (
            RunStatus.COMPLETED_WITH_GAPS
            if result.evidence_gap_count
            else RunStatus.COMPLETED
        )
        completed = replace(
            retrying,
            status=status,
            completed_at=now,
            result_ref=result.result_ref,
            evidence_gap_count=result.evidence_gap_count,
        )
        self.store.save_run(completed)
        self._event(completed, "run_completed", status.value, status.value, now=now)
        schedule = self.store.get_schedule(run.schedule_id)
        if schedule is not None:
            self.store.save_schedule(
                replace(schedule, last_successful_run=now).advance(
                    after=run.scheduled_for
                )
            )
        return completed

    def mark_missed(
        self, *, now: datetime, reason: str = "scheduler_resumed_after_due_window"
    ) -> DailyRun:
        schedule = self.initialise(now=now)
        assert schedule.next_expected_run is not None
        if now < schedule.next_expected_run:
            latest = self.store.latest_run()
            if latest is not None and latest.status is RunStatus.MISSED:
                return latest
            raise ValueError("no scheduled run has been missed")
        existing = self.store.get_run_for_schedule_time(schedule.next_expected_run)
        if existing is not None:
            return existing
        run = DailyRun(
            DailyRun.deterministic_id(schedule.schedule_id, schedule.next_expected_run),
            schedule.schedule_id,
            schedule.next_expected_run,
            1,
            RunStatus.MISSED,
            now,
            completed_at=now,
            failure_code=RunFailureCode.SCHEDULER_INTERRUPTED.value,
            failure_detail=reason,
            missed_reason=reason,
            retry_safe=True,
        )
        self.store.save_run(run)
        self._event(run, "run_missed", "scheduled_window_missed", "missed", now=now)
        self.store.save_schedule(schedule.advance(after=schedule.next_expected_run))
        return run

    def status(self, *, now: datetime) -> DailyOperationalStatus:
        schedule = self.initialise(now=now)
        latest = self.store.latest_run()
        run_due = (
            schedule.next_expected_run is not None and now >= schedule.next_expected_run
        )
        healthy = latest is not None and latest.status in {
            RunStatus.COMPLETED,
            RunStatus.COMPLETED_WITH_GAPS,
        }
        attention = latest is not None and latest.status in {
            RunStatus.FAILED,
            RunStatus.MISSED,
        }
        return DailyOperationalStatus(
            schedule.schedule_id,
            "Due"
            if run_due and not attention
            else "Healthy"
            if healthy and not attention
            else "Attention required"
            if attention
            else "Not yet run",
            schedule.last_successful_run,
            latest,
            schedule.next_expected_run,
            attention,
            True,
            run_due,
        )

    def _fail(
        self, run: DailyRun, now: datetime, code: RunFailureCode, detail: str
    ) -> DailyRun:
        failed = replace(
            run,
            status=RunStatus.FAILED,
            completed_at=now,
            failure_code=code.value,
            failure_detail=detail,
            retry_safe=True,
        )
        self.store.save_run(failed)
        self._event(failed, "run_failed", code.value, "failed", now=now)
        return failed

    def _event(
        self,
        run: DailyRun,
        event_type: str,
        reason: str,
        outcome: str,
        *,
        now: datetime,
    ) -> None:
        self.store.append_audit(
            AuditEvent(
                f"daily-event:{uuid4().hex}",
                event_type,
                now,
                run.run_id,
                reason,
                outcome,
            )
        )


def _at_local(day: date, local_time: time) -> datetime:
    return datetime.combine(day, local_time, tzinfo=_ZONE)


def _aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")


def _format(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _parse(value: object) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))


def _display(value: datetime | None) -> str:
    return "unknown" if value is None else value.astimezone(_ZONE).isoformat()
