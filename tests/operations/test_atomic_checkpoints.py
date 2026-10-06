"""Event and record-count checkpoints share one crash-safe SQLite commit."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.outlook import ingest_mailbox
from edn.operations.storage import EventStore
from tests.operations.test_import_outcomes import Pages, stores
from tests.operations.test_outlook import END, MAILBOX, START, message


@pytest.mark.parametrize("duplicate", [False, True])
def test_checkpoint_failure_rolls_back_record_and_keeps_original_counts(
    tmp_path, monkeypatch, duplicate
):
    events, outcomes = stores(tmp_path)
    if duplicate:
        ingest_mailbox(
            Pages({"value": [message()]}),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    original = outcomes.update

    def broken(*args, **kwargs):
        if (
            kwargs.get("connection") is not None
            and kwargs.get("state", "in_progress") == "in_progress"
        ):
            original(*args, **kwargs)
            raise RuntimeError("PRIVATE_CHECKPOINT_ERROR")
        return original(*args, **kwargs)

    monkeypatch.setattr(outcomes, "update", broken)
    with pytest.raises(RuntimeError):
        ingest_mailbox(
            Pages({"value": [message()]}),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    failed = outcomes.latest()[0]
    assert failed.state == "failed" and failed.inserted == failed.duplicates == 0
    assert len(events.list_events()) == int(duplicate)
    monkeypatch.setattr(outcomes, "update", original)
    replay = ingest_mailbox(
        Pages({"value": [message()]}), events, MAILBOX, START, END, outcomes=outcomes
    )
    assert (replay.inserted, replay.duplicates) == (int(not duplicate), int(duplicate))
    assert len(events.list_events()) == 1


def test_hard_exit_inside_checkpoint_rolls_back_event_and_counts(tmp_path):
    events, outcomes = stores(tmp_path)
    code = """
import os, sys
from pathlib import Path
from edn.operations.storage import EventStore
from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.outlook import ingest_mailbox
from tests.operations.test_import_outcomes import Pages
from tests.operations.test_outlook import START, END, MAILBOX, message
events = EventStore(Path(sys.argv[1]))
outcomes = ImportOutcomeStore(events.path)
original = outcomes.update
def terminate(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(77)
outcomes.update = terminate
ingest_mailbox(
    Pages({'value': [message()]}), events, MAILBOX, START, END, outcomes=outcomes
)
"""
    root = Path(__file__).resolve().parents[2]
    environment = dict(
        os.environ, PYTHONPATH=os.pathsep.join((str(root / "src"), str(root)))
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(events.path)],
        cwd=root,
        env=environment,
        capture_output=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 77, result.stderr.decode()
    checkpoint = outcomes.latest()[0]
    assert checkpoint.state == "in_progress" and checkpoint.inserted == 0
    assert events.list_events() == ()
    with sqlite3.connect(events.path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
    replay = ingest_mailbox(
        Pages({"value": [message()]}), events, MAILBOX, START, END, outcomes=outcomes
    )
    assert replay.inserted == 1 and replay.complete


@pytest.mark.parametrize("kind", ["different", "readonly-events", "readonly-outcomes"])
def test_invalid_checkpoint_pair_refused_before_source_access(tmp_path, kind):
    events, outcomes = stores(tmp_path)
    if kind == "different":
        other = tmp_path / "other"
        other.mkdir()
        _, outcomes = stores(other)
    elif kind == "readonly-events":
        events = EventStore(events.path, read_only=True)
    else:
        outcomes = ImportOutcomeStore(events.path, read_only=True)

    class NoReads:
        def page(self, *args, **kwargs):
            pytest.fail("Invalid checkpoint pair reached source")

    before = events.path.read_bytes(), outcomes.path.read_bytes()
    with pytest.raises(ValueError):
        ingest_mailbox(NoReads(), events, MAILBOX, START, END, outcomes=outcomes)
    assert before == (events.path.read_bytes(), outcomes.path.read_bytes())


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize(
    "mutation", ["event-version", "outcome-version", "table-shape"]
)
def test_shared_and_normal_updates_preserve_schema_gates(tmp_path, shared, mutation):
    events, outcomes = stores(tmp_path)
    run = outcomes.begin(MAILBOX, START, END)
    with sqlite3.connect(events.path) as connection:
        if mutation == "event-version":
            connection.execute("PRAGMA user_version=2")
        elif mutation == "outcome-version":
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("UPDATE operations_import_outcomes SET schema_version=2")
        else:
            connection.execute(
                "ALTER TABLE operations_import_outcomes ADD COLUMN unexpected TEXT"
            )
    before = events.path.read_bytes()
    if shared:
        connection = sqlite3.connect(events.path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            with pytest.raises(ValueError):
                outcomes.update(
                    run,
                    inserted=1,
                    duplicates=0,
                    failed=0,
                    pages=0,
                    connection=connection,
                )
            connection.rollback()
        finally:
            connection.close()
    else:
        with pytest.raises(ValueError):
            outcomes.update(run, inserted=1, duplicates=0, failed=0, pages=0)
    assert events.path.read_bytes() == before
