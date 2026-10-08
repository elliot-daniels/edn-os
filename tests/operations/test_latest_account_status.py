"""Busy-account retries must not hide another account's latest incomplete run."""

import json
import sqlite3
from dataclasses import asdict

import pytest

from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.storage import EventStore
from tests.operations.test_import_outcomes import stores
from tests.operations.test_outlook import END, MAILBOX, START


def test_busy_account_does_not_evict_other_latest_status(tmp_path, monkeypatch):
    from edn.ui import operations

    events, outcomes = stores(tmp_path)
    other = "other@example.invalid"
    run = outcomes.begin(other, START, END)
    outcomes.update(
        run,
        inserted=1,
        duplicates=0,
        failed=0,
        pages=1,
        state="partial",
        reason="import_error",
    )
    for _ in range(25):
        busy = outcomes.begin(MAILBOX, START, END)
        outcomes.update(
            busy, inserted=0, duplicates=0, failed=0, pages=1, state="complete"
        )
    before = events.path.read_bytes()
    reader = ImportOutcomeStore(events.path, read_only=True)
    latest = reader.latest_per_account()
    assert {item.source_account for item in latest} == {MAILBOX, other}
    assert (
        next(item for item in latest if item.source_account == other).state == "partial"
    )
    assert len(reader.latest()) == 20  # Existing attempt-history API is unchanged.
    displayed = []
    for method in ("caption", "text", "warning"):
        monkeypatch.setattr(operations.st, method, displayed.append)
    operations.render_import_status(events.path)
    assert f"Import status: Partial · {other}" in displayed
    assert f"Import status: Complete · {MAILBOX}" in displayed
    assert "up to 20 accounts" in "\n".join(displayed)
    assert events.path.read_bytes() == before
    assert "body" not in json.dumps([asdict(item) for item in latest])


def test_account_bound_and_tied_run_order_are_deterministic(tmp_path):
    events, outcomes = stores(tmp_path)
    first = outcomes.begin(MAILBOX, START, END)
    second = outcomes.begin(MAILBOX, START, END)
    other = outcomes.begin("other@example.invalid", START, END)
    with sqlite3.connect(events.path) as connection:
        connection.execute(
            "UPDATE operations_import_outcomes SET started_at=?", (START.isoformat(),)
        )
    reader = ImportOutcomeStore(events.path, read_only=True)
    assert [item.run_id for item in reader.latest_per_account()] == sorted(
        [max(first, second), other], reverse=True
    )
    assert len(reader.latest_per_account(limit=1)) == 1


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_invalid_account_bound_is_refused_before_opening(tmp_path, limit):
    path = tmp_path / "missing.db"
    with pytest.raises(ValueError):
        ImportOutcomeStore(path, read_only=True).latest_per_account(limit=limit)
    assert not path.exists()


def test_legacy_missing_and_future_schemas_remain_read_only(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        ImportOutcomeStore(missing, read_only=True).latest_per_account()
    assert not missing.exists()
    legacy = EventStore(tmp_path / "legacy.db")
    legacy.initialise()
    before = legacy.path.read_bytes()
    assert ImportOutcomeStore(legacy.path, read_only=True).latest_per_account() == ()
    assert legacy.path.read_bytes() == before
    events, _ = stores(tmp_path)
    with sqlite3.connect(events.path) as connection:
        connection.execute("PRAGMA user_version=2")
    before = events.path.read_bytes()
    with pytest.raises(ValueError, match="schema"):
        ImportOutcomeStore(events.path, read_only=True).latest_per_account()
    assert events.path.read_bytes() == before
