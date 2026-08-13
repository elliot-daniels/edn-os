"""Synthetic PA-008 scheduling, lifecycle, observability, and backup tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from edn.intelligence import (
    BackupComponent,
    BriefRunResult,
    DailyIntelligenceScheduler,
    DailyOperationsStore,
    DailySchedule,
    OperationalBackup,
    RunFailureCode,
    RunStatus,
)

ADELAIDE = ZoneInfo("Australia/Adelaide")
SCHEDULED = datetime(2026, 8, 14, 8, 0, tzinfo=ADELAIDE)
NOW = datetime(2026, 8, 14, 9, 0, tzinfo=ADELAIDE)


def _scheduler(tmp_path: Path) -> DailyIntelligenceScheduler:
    store = DailyOperationsStore(tmp_path / "daily-operations.db")
    return DailyIntelligenceScheduler(
        store,
        DailySchedule(next_expected_run=SCHEDULED),
    )


def test_schedule_is_adelaide_timezone_aware_and_dst_safe() -> None:
    schedule = DailySchedule(local_time=time(8, 0))
    before_dst = schedule.initialise(now=datetime(2026, 10, 2, 10, 0, tzinfo=UTC))
    assert before_dst.next_expected_run is not None
    assert before_dst.next_expected_run.astimezone(ADELAIDE).time() == time(8, 0)
    after = before_dst.advance(after=before_dst.next_expected_run)
    assert after.next_expected_run is not None
    assert after.next_expected_run.astimezone(ADELAIDE).time() == time(8, 0)
    assert (
        after.next_expected_run.utcoffset() != before_dst.next_expected_run.utcoffset()
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        schedule.initialise(now=datetime(2026, 8, 14, 9, 0))


def test_due_run_completes_and_repeated_ticks_are_idempotent(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    calls: list[str] = []

    def runner() -> BriefRunResult:
        calls.append("run")
        return BriefRunResult("brief:synthetic", evidence_gap_count=0)

    first = scheduler.tick(now=NOW, runner=runner)
    second = scheduler.tick(now=NOW + timedelta(minutes=1), runner=runner)

    assert first is not None and first.status is RunStatus.COMPLETED
    assert second is None
    assert calls == ["run"]
    assert len(scheduler.store.history(first.run_id)) == 3
    status = scheduler.status(now=NOW + timedelta(minutes=1))
    assert status.health == "Healthy"
    assert "Status: Healthy" in status.render()
    assert "Latest attempt: Complete" in status.render()

    next_schedule = scheduler.store.get_schedule("daily-intelligence")
    assert next_schedule is not None and next_schedule.next_expected_run is not None
    due_status = scheduler.status(now=next_schedule.next_expected_run)
    assert due_status.run_due is True
    assert due_status.health == "Due"
    assert "Today's run" not in due_status.render()


def test_completed_with_gaps_is_successful_but_observable(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    run = scheduler.tick(
        now=NOW,
        runner=lambda: BriefRunResult("brief:gapped", evidence_gap_count=2),
    )
    assert run is not None and run.status is RunStatus.COMPLETED_WITH_GAPS
    assert run.evidence_gap_count == 2
    assert scheduler.status(now=NOW).health == "Healthy"


def test_authority_failure_is_recorded_and_never_bypassed(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    run = scheduler.tick(
        now=NOW,
        runner=lambda: (_ for _ in ()).throw(PermissionError("not authorised")),
    )
    assert run is not None and run.status is RunStatus.FAILED
    assert run.failure_code == RunFailureCode.AUTHORITY_DENIED.value
    assert scheduler.status(now=NOW).recovery_required is True


def test_failure_preserves_last_success_and_safe_retry_is_explicit(
    tmp_path: Path,
) -> None:
    scheduler = _scheduler(tmp_path)
    successful = scheduler.tick(
        now=NOW,
        runner=lambda: BriefRunResult("brief:good"),
    )
    assert successful is not None
    next_schedule = scheduler.store.get_schedule("daily-intelligence")
    assert next_schedule is not None and next_schedule.next_expected_run is not None
    due_again = next_schedule.next_expected_run
    scheduler.store.save_schedule(
        DailySchedule(
            next_expected_run=due_again,
            last_successful_run=successful.completed_at,
        )
    )

    failed = scheduler.tick(
        now=due_again + timedelta(minutes=2),
        runner=lambda: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
    )
    assert failed is not None and failed.status is RunStatus.FAILED
    assert failed.failure_code == RunFailureCode.BRIEF_ASSEMBLY_FAILED.value
    status = scheduler.status(now=due_again + timedelta(minutes=2))
    assert status.last_successful_run == successful.completed_at
    assert status.recovery_required is True
    assert "Reason: brief_assembly_failed" in status.render()

    retried = scheduler.retry(
        failed.run_id,
        now=due_again + timedelta(minutes=3),
        runner=lambda: BriefRunResult("brief:recovered"),
    )
    assert retried.status is RunStatus.COMPLETED
    assert retried.attempt == 2
    assert scheduler.store.get_run(failed.run_id) == retried


def test_missed_run_is_explicit_and_does_not_create_backlog(tmp_path: Path) -> None:
    scheduler = _scheduler(tmp_path)
    missed_at = NOW + timedelta(hours=12)
    missed = scheduler.mark_missed(now=missed_at)
    repeated = scheduler.mark_missed(now=missed_at + timedelta(minutes=1))
    assert missed.status is RunStatus.MISSED
    assert missed.retry_safe is True
    assert repeated.run_id == missed.run_id
    assert scheduler.status(now=missed_at).recovery_required is True


def test_backup_manifest_integrity_restore_and_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "daily-operations.db"
    source.write_bytes(b"synthetic operational state")
    backup_dir = tmp_path / "backup"
    backup = OperationalBackup()
    manifest = backup.create(
        backup_dir,
        components=(BackupComponent("daily_operations", source),),
        now=NOW,
    )
    assert manifest.components[0][0] == "daily_operations"
    assert "authentication_tokens" in manifest.excluded_components
    assert backup.verify(backup_dir) == manifest
    restored = tmp_path / "restored"
    assert backup.restore(backup_dir, restored) == manifest
    assert (restored / "000-daily_operations.bin").read_bytes() == source.read_bytes()
    with pytest.raises(FileExistsError, match="cannot be overwritten"):
        backup.restore(backup_dir, restored)

    (backup_dir / manifest.components[0][3]).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity failed"):
        backup.verify(backup_dir)

    backup_dir = tmp_path / "incomplete-backup"
    incomplete = backup.create(
        backup_dir,
        components=(BackupComponent("daily_operations", source),),
    )
    (backup_dir / incomplete.components[0][3]).unlink()
    with pytest.raises(ValueError, match="integrity failed"):
        backup.verify(backup_dir)


def test_backup_rejects_missing_component_prohibited_material_and_bad_schema(
    tmp_path: Path,
) -> None:
    backup = OperationalBackup()
    with pytest.raises(FileNotFoundError):
        backup.create(
            tmp_path / "missing-backup",
            components=(BackupComponent("missing", tmp_path / "missing.db"),),
        )
    secret = tmp_path / "secret-token.db"
    secret.write_bytes(b"do not copy")
    with pytest.raises(PermissionError, match="prohibited"):
        backup.create(
            tmp_path / "secret-backup",
            components=(BackupComponent("secret", secret),),
        )
    source = tmp_path / "state.db"
    source.write_bytes(b"state")
    with pytest.raises(PermissionError, match="prohibited"):
        backup.create(
            tmp_path / "named-secret-backup",
            components=(BackupComponent("authentication_tokens", source),),
        )
    backup_dir = tmp_path / "schema-backup"
    backup.create(backup_dir, components=(BackupComponent("state", source),))
    manifest_path = backup_dir / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 999
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        backup.verify(backup_dir)


def test_backup_manifest_never_contains_raw_content_or_token_strings(
    tmp_path: Path,
) -> None:
    source = tmp_path / "safe.db"
    source.write_bytes(b"synthetic source state")
    backup_dir = tmp_path / "backup"
    OperationalBackup().create(
        backup_dir,
        components=(BackupComponent("safe_state", source),),
    )
    manifest_text = (backup_dir / "manifest.json").read_text(encoding="utf-8")
    assert "synthetic source state" not in manifest_text
    assert "token" in manifest_text
