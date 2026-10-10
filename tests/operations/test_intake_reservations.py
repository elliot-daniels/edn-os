"""Synthetic reservation lifecycle, races, integrity and platform refusal."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from itertools import pairwise
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.operations.intake_security import IntakeSecurityError
from tests.operations.test_intake_scheduling import NOW, event, request, snapshot


def store(tmp_path):
    result = SyntheticReservationStore(tmp_path / "reservations.db")
    if os.name != "posix":
        before = tuple(tmp_path.iterdir())
        with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
            result.initialise()
        assert tuple(tmp_path.iterdir()) == before
        return None
    tmp_path.chmod(0o700)
    result.initialise()
    return result


def save(ledger, job=None, calendar=None, **kwargs):
    defaults = dict(
        job_revision=1,
        job_hash="a" * 64,
        expected_revision=0,
        now=NOW,
        actor="synthetic-operator",
    )
    defaults.update(kwargs)
    return ledger.reserve(
        job or replace(request(), job_id=str(uuid4())),
        calendar or snapshot(),
        **defaults,
    )


def test_restart_and_replay_preserve_exact_receipt(tmp_path):
    ledger = store(tmp_path)
    if ledger is None:
        return
    job = replace(request(), job_id=str(uuid4()))
    first = save(ledger, job)
    reopened = SyntheticReservationStore(tmp_path / "reservations.db")
    assert reopened.list_reservations() == (first,)
    assert save(reopened, job) == first
    assert first["state"] == "provisional"
    assert first["history"][0]["job_hash"] == "a" * 64
    assert "Awaiting Confirmation" in first["history"][0]["plan"]["title"]
    assert (tmp_path / "reservations.db").stat().st_mode & 0o777 == 0o600


def test_concurrent_jobs_never_overlap_including_travel_buffers(tmp_path):
    ledger = store(tmp_path)
    if ledger is None:
        return
    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = list(executor.map(lambda _: save(ledger), range(4)))
    from datetime import datetime

    spans = sorted(
        (
            datetime.fromisoformat(r["history"][-1]["plan"]["occupied_start"]),
            datetime.fromisoformat(r["history"][-1]["plan"]["occupied_end"]),
        )
        for r in rows
    )
    assert all(a[1] <= b[0] for a, b in pairwise(spans))
    assert len(ledger.list_reservations()) == 4


def test_reschedule_and_cancel_keep_history_and_release_occupied_interval(tmp_path):
    ledger = store(tmp_path)
    if ledger is None:
        return
    job = replace(request(), job_id=str(uuid4()))
    original = save(ledger, job)
    changed = replace(job, requested_date=(NOW + timedelta(days=1)).date())
    with pytest.raises(IntakeError, match="refresh"):
        save(ledger, changed)
    revised = save(
        ledger, changed, expected_revision=1, job_revision=2, job_hash="b" * 64
    )
    assert revised["history"][0] == original["history"][0]
    assert revised["history"][1]["action"] == "rescheduled"
    assert (
        revised["history"][1]["plan"]["reservation_key"]
        == original["history"][0]["plan"]["reservation_key"]
    )
    cancelled = ledger.cancel(
        job.job_id, 2, actor="operator", reason="Synthetic cancellation", now=NOW
    )
    assert cancelled["revision"] == 3 and cancelled["state"] == "cancelled"
    assert cancelled["history"][:2] == revised["history"]
    assert (
        ledger.cancel(job.job_id, 3, actor="operator", reason="Replay", now=NOW)
        == cancelled
    )
    next_job = save(ledger, replace(changed, job_id=str(uuid4())))
    assert (
        next_job["history"][0]["plan"]["occupied_start"]
        == revised["history"][1]["plan"]["occupied_start"]
    )


def test_conflict_does_not_replace_existing_reservation(tmp_path):
    ledger = store(tmp_path)
    if ledger is None:
        return
    job = replace(request(), job_id=str(uuid4()))
    first = save(ledger, job)
    changed = replace(job, requested_start=NOW + timedelta(hours=2))
    busy = event(NOW, NOW + timedelta(hours=5))
    with pytest.raises(IntakeError, match="conflict-free"):
        save(ledger, changed, snapshot(events=(busy,)), expected_revision=1)
    assert ledger.list_reservations() == (first,)


@pytest.mark.parametrize(
    "case", ["incomplete", "stale", "uncertain", "live", "hash", "revision"]
)
def test_invalid_evidence_never_creates_reservation(tmp_path, case):
    ledger = store(tmp_path)
    if ledger is None:
        return
    job = replace(request(), job_id=str(uuid4()))
    calendar = snapshot()
    kwargs = {}
    if case == "incomplete":
        calendar = replace(calendar, complete=False)
    elif case == "stale":
        calendar = replace(calendar, checked_at=NOW - timedelta(minutes=6))
    elif case == "uncertain":
        job = replace(job, duration=replace(job.duration, reliable=False))
    elif case == "live":
        calendar = replace(calendar, scope_ref="owner-calendar")
    elif case == "hash":
        kwargs["job_hash"] = "invalid"
    else:
        kwargs["expected_revision"] = True
    with pytest.raises(IntakeError):
        save(ledger, job, calendar, **kwargs)
    assert ledger.list_reservations() == ()


def test_corrupt_occupied_data_blocks_new_bookings(tmp_path):
    ledger = store(tmp_path)
    if ledger is None:
        return
    first = save(ledger)
    first["history"][0]["plan"]["occupied_end"] = "invalid"
    with ledger._backend._connect() as connection:
        connection.execute("UPDATE reservations SET record=?", (json.dumps(first),))
    with pytest.raises(IntakeError, match="integrity"):
        save(ledger)


def test_read_only_and_version_hash_conflicts_cannot_mutate(tmp_path):
    ledger = store(tmp_path)
    if ledger is None:
        return
    job = replace(request(), job_id=str(uuid4()))
    first = save(ledger, job)
    with pytest.raises(IntakeError, match="version/hash"):
        save(ledger, job, expected_revision=1, job_hash="b" * 64)
    read_only = SyntheticReservationStore(tmp_path / "reservations.db", read_only=True)
    assert read_only.list_reservations() == (first,)
    with pytest.raises(IntakeError, match="Read-only"):
        read_only.cancel(job.job_id, 1, actor="operator", reason="Test", now=NOW)
