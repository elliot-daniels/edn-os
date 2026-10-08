"""Synthetic durable import completeness and restart/failure evidence."""

import json
import sqlite3
from dataclasses import asdict

import pytest

from edn.operations.cli import main
from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.outlook import ingest_mailbox
from edn.operations.storage import EventStore
from tests.operations.test_outlook import END, MAILBOX, NEXT, START, message


class Pages:
    def __init__(self, *pages):
        self.pages = iter(pages)

    def page(self, *args, **kwargs):
        value = next(self.pages)
        if isinstance(value, BaseException):
            raise value
        return value


def stores(tmp_path):
    events = EventStore(tmp_path / "events.db")
    events.initialise()
    outcomes = ImportOutcomeStore(events.path)
    outcomes.initialise()
    return events, outcomes


def test_success_and_replay_retain_distinct_durable_attempts(tmp_path):
    events, outcomes = stores(tmp_path)
    for _ in range(2):
        report = ingest_mailbox(
            Pages({"value": [message()]}),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
        assert report.complete
    history = ImportOutcomeStore(events.path, read_only=True).latest()
    assert len(history) == 2
    assert history[0].state == history[1].state == "complete"
    assert (history[0].inserted, history[0].duplicates, history[0].pages) == (0, 1, 1)
    assert history[0].run_id != history[1].run_id
    assert history[0].window_start == START.isoformat()
    assert history[0].source_account == MAILBOX


@pytest.mark.parametrize(
    "interruption",
    [
        RuntimeError("sensitive bearer/source body"),
        ValueError("sensitive invalid continuation"),
    ],
)
def test_later_failure_retains_partial_counts_without_exception_contents(
    tmp_path, interruption
):
    events, outcomes = stores(tmp_path)
    client = Pages({"value": [message()], "@odata.nextLink": NEXT}, interruption)
    with pytest.raises(type(interruption)):
        ingest_mailbox(client, events, MAILBOX, START, END, outcomes=outcomes)
    outcome = ImportOutcomeStore(events.path, read_only=True).latest()[0]
    assert (outcome.state, outcome.inserted, outcome.pages, outcome.reason) == (
        "partial",
        1,
        1,
        "import_error",
    )
    assert outcome.finished_at is not None
    assert "sensitive" not in json.dumps(asdict(outcome))
    assert "Source body" not in json.dumps(asdict(outcome))
    replay = ingest_mailbox(
        Pages({"value": [message()]}), events, MAILBOX, START, END, outcomes=outcomes
    )
    assert replay.inserted == 0 and replay.duplicates == 1


def test_first_page_failure_is_durable_failed(tmp_path):
    events, outcomes = stores(tmp_path)
    with pytest.raises(RuntimeError):
        ingest_mailbox(
            Pages(RuntimeError("synthetic")),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    outcome = outcomes.latest()[0]
    assert outcome.state == "failed" and outcome.pages == outcome.inserted == 0


@pytest.mark.parametrize(
    "page,limit,reason",
    [
        ({"value": [message(), {"id": "bad"}]}, 100, "malformed_records"),
        ({"value": [message()], "@odata.nextLink": NEXT}, 1, "page_limit"),
    ],
)
def test_malformed_and_bounded_runs_are_partial(tmp_path, page, limit, reason):
    events, outcomes = stores(tmp_path)
    report = ingest_mailbox(
        Pages(page), events, MAILBOX, START, END, max_pages=limit, outcomes=outcomes
    )
    assert not report.complete
    outcome = outcomes.latest()[0]
    assert outcome.state == "partial" and outcome.reason == reason


def test_catchable_interrupt_is_durable_partial_after_restart(tmp_path):
    events, outcomes = stores(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        ingest_mailbox(
            Pages({"value": [message()], "@odata.nextLink": NEXT}, KeyboardInterrupt()),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    outcome = ImportOutcomeStore(events.path, read_only=True).latest()[0]
    assert outcome.state == "partial" and outcome.finished_at is not None
    assert outcome.reason == "import_error"
    assert outcome.inserted == outcome.pages == 1


def test_read_only_status_does_not_initialize_missing_database(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        ImportOutcomeStore(path, read_only=True).latest()
    assert not path.exists()
    events = EventStore(tmp_path / "legacy.db")
    events.initialise()
    assert ImportOutcomeStore(events.path, read_only=True).latest() == ()
    with pytest.raises(ValueError, match="Read-only"):
        ImportOutcomeStore(events.path, read_only=True).initialise()


def test_cli_import_status_reads_metadata_without_authentication(tmp_path, capsys):
    events, outcomes = stores(tmp_path)
    ingest_mailbox(Pages({"value": []}), events, MAILBOX, START, END, outcomes=outcomes)
    assert (
        main(
            [
                "import-status",
                "--database",
                str(events.path),
                "--data-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["coverage"] == "requested_inbox_windows_only"
    assert status["runs"][0]["state"] == "complete"
    assert "body" not in status["runs"][0]


@pytest.mark.parametrize(
    "kind,label",
    [
        ("malformed", "Partial"),
        ("network", "Partial"),
        ("failed", "Failed"),
        ("interrupted", "Partial"),
        ("complete", "Complete"),
        ("never", "never run"),
    ],
)
def test_inbox_status_survives_restart_and_reports_bounded_completeness(
    tmp_path, monkeypatch, kind, label
):
    from edn.ui import operations

    events, outcomes = stores(tmp_path)
    if kind == "malformed":
        ingest_mailbox(
            Pages({"value": [message(), {"id": "bad"}]}),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    elif kind == "complete":
        ingest_mailbox(
            Pages({"value": []}), events, MAILBOX, START, END, outcomes=outcomes
        )
    elif kind != "never":
        error = (
            KeyboardInterrupt()
            if kind == "interrupted"
            else RuntimeError("SECRET_SOURCE_BODY")
        )
        pages = (
            [error]
            if kind == "failed"
            else [{"value": [message()], "@odata.nextLink": NEXT}, error]
        )
        with pytest.raises(type(error)):
            ingest_mailbox(
                Pages(*pages), events, MAILBOX, START, END, outcomes=outcomes
            )
    displayed = []
    for method in ("info", "warning", "caption", "text"):
        monkeypatch.setattr(operations.st, method, displayed.append)
    operations.render_import_status(events.path)
    rendered = "\n".join(displayed)
    assert label in rendered
    assert "SECRET_SOURCE_BODY" not in rendered
    assert "Source body" not in rendered
    if kind != "never":
        assert "requested Inbox window" in rendered


def test_cli_failure_prints_only_sanitized_durable_outcomes(
    tmp_path, monkeypatch, capsys
):
    from edn.operations import cli

    events, _ = stores(tmp_path)
    client = Pages(
        {"value": [message()], "@odata.nextLink": NEXT},
        RuntimeError("SECRET_TOKEN_BODY"),
    )
    client.account = lambda: {"mail": MAILBOX}
    monkeypatch.setattr(cli, "DeviceCodeCredential", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "OperationsOutlookClient", lambda *args, **kwargs: client)
    monkeypatch.setenv("EDN_OPERATIONS_MAILBOXES", MAILBOX)
    monkeypatch.setenv("EDN_MS_TENANT_ID", "synthetic-tenant")
    monkeypatch.setenv("EDN_MS_CLIENT_ID", "synthetic-client")
    result = main(
        [
            "ingest-outlook",
            "--database",
            str(events.path),
            "--data-root",
            str(tmp_path),
            "--start",
            START.isoformat(),
            "--end",
            END.isoformat(),
        ]
    )
    output = capsys.readouterr().out
    assert result == 1
    assert "SECRET_TOKEN_BODY" not in output
    assert "Source body" not in output
    record = json.loads(output)
    assert record["recent_outcomes"][0]["state"] == "partial"
    assert record["recent_outcomes"][0]["inserted"] == 1


def test_incompatible_outcome_schema_fails_closed_without_writing(tmp_path):
    events, outcomes = stores(tmp_path)
    with sqlite3.connect(events.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        run = outcomes.begin(MAILBOX, START, END)
        connection.execute(
            "UPDATE operations_import_outcomes SET schema_version=2 WHERE run_id=?",
            (run,),
        )
    before = events.path.read_bytes()
    for action in (
        outcomes.initialise,
        outcomes.latest,
        lambda: outcomes.begin(MAILBOX, START, END),
    ):
        with pytest.raises(ValueError, match="schema"):
            action()
    assert events.path.read_bytes() == before


@pytest.mark.parametrize("count", [True, 1.5, "1", -1])
def test_outcome_updates_reject_noninteger_counts(tmp_path, count):
    _, outcomes = stores(tmp_path)
    run = outcomes.begin(MAILBOX, START, END)
    with pytest.raises(ValueError):
        outcomes.update(run, inserted=count, duplicates=0, failed=0, pages=0)
    assert outcomes.latest()[0].inserted == 0


def test_blank_account_filter_is_rejected(tmp_path):
    _, outcomes = stores(tmp_path)
    with pytest.raises(ValueError, match="nonblank"):
        outcomes.latest(account="")


@pytest.mark.parametrize("command", ["init", "ingest-outlook"])
def test_future_event_schema_rejected_before_auth_or_writes(
    tmp_path, monkeypatch, command
):
    from edn.operations import cli

    events, outcomes = stores(tmp_path)
    with sqlite3.connect(events.path) as connection:
        connection.execute("PRAGMA user_version=2")
    before = events.path.read_bytes()
    monkeypatch.setattr(
        cli,
        "DeviceCodeCredential",
        lambda *args, **kwargs: pytest.fail("Authentication must not begin"),
    )
    with pytest.raises(SystemExit):
        main(
            [
                command,
                "--database",
                str(events.path),
                "--data-root",
                str(tmp_path),
                "--start",
                START.isoformat(),
                "--end",
                END.isoformat(),
            ]
        )
    assert events.path.read_bytes() == before
    with pytest.raises(ValueError, match="Event schema"):
        outcomes.initialise()


@pytest.mark.parametrize(
    "column,value",
    [
        ("state", "unknown"),
        ("window_start", "source body"),
        ("run_id", "raw exception"),
        ("finished_at", "2026-10-06T00:00:00"),
        ("failed", -1),
    ],
)
def test_corrupt_outcome_history_fails_closed_in_inbox(
    tmp_path, monkeypatch, column, value
):
    from edn.ui import operations

    events, outcomes = stores(tmp_path)
    ingest_mailbox(Pages({"value": []}), events, MAILBOX, START, END, outcomes=outcomes)
    with sqlite3.connect(events.path) as connection:
        connection.execute(
            f"UPDATE operations_import_outcomes SET {column}=?", (value,)
        )
    before = events.path.read_bytes()
    displayed = []
    monkeypatch.setattr(operations.st, "warning", displayed.append)
    operations.render_import_status(events.path)
    assert displayed == ["Import history is unavailable; completeness is unknown."]
    assert events.path.read_bytes() == before


@pytest.mark.parametrize(
    "definition",
    [
        "run_id TEXT",
        "run_id TEXT PRIMARY KEY, "
        "schema_version INTEGER NOT NULL CHECK(schema_version=2)",
    ],
)
def test_empty_incompatible_outcome_table_is_not_adopted(tmp_path, definition):
    events = EventStore(tmp_path / "events.db")
    events.initialise()
    with sqlite3.connect(events.path) as connection:
        connection.execute(
            "CREATE TABLE operations_import_outcomes (" + definition + ")"
        )
    before = events.path.read_bytes()
    outcomes = ImportOutcomeStore(events.path)
    for action in (outcomes.initialise, outcomes.latest):
        with pytest.raises(ValueError, match="table schema"):
            action()
    assert events.path.read_bytes() == before


def test_checkpoint_interrupt_keeps_replay_safe_incomplete_evidence(
    tmp_path, monkeypatch
):
    events, outcomes = stores(tmp_path)
    original = outcomes.update

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(outcomes, "update", interrupted)
    with pytest.raises(KeyboardInterrupt):
        ingest_mailbox(
            Pages({"value": [message()]}),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    checkpoint = ImportOutcomeStore(events.path, read_only=True).latest()[0]
    assert checkpoint.state == "in_progress" and checkpoint.inserted == 0
    assert len(events.list_events()) == 1
    monkeypatch.setattr(outcomes, "update", original)
    replay = ingest_mailbox(
        Pages({"value": [message()]}), events, MAILBOX, START, END, outcomes=outcomes
    )
    assert replay.inserted == 0 and replay.duplicates == 1


def test_complete_outcome_cannot_hide_failures(tmp_path):
    _, outcomes = stores(tmp_path)
    run = outcomes.begin(MAILBOX, START, END)
    with pytest.raises(ValueError, match="Complete"):
        outcomes.update(
            run, inserted=0, duplicates=0, failed=1, pages=1, state="complete"
        )
    assert outcomes.latest()[0].state == "in_progress"


@pytest.mark.parametrize("kind", ["malformed", "network"])
def test_streamlit_inbox_shows_reopened_partial_run(tmp_path, monkeypatch, kind):
    from streamlit.testing.v1 import AppTest

    from tests.ui.test_operations import APP

    events, outcomes = stores(tmp_path)
    if kind == "malformed":
        ingest_mailbox(
            Pages({"value": [message(), {"id": "bad"}]}),
            events,
            MAILBOX,
            START,
            END,
            outcomes=outcomes,
        )
    else:
        with pytest.raises(RuntimeError):
            ingest_mailbox(
                Pages(
                    {"value": [message()], "@odata.nextLink": NEXT},
                    RuntimeError("PRIVATE_FAILURE_DETAIL"),
                ),
                events,
                MAILBOX,
                START,
                END,
                outcomes=outcomes,
            )
    monkeypatch.setenv("EDN_OPERATIONS_DB", str(events.path))
    monkeypatch.delenv("EDN_MEMORY_DB", raising=False)
    before = events.path.read_bytes()
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert any("Import status: Partial" in item.value for item in app.text)
    captions = "\n".join(item.value for item in app.caption)
    assert "requested Inbox window" in captions
    assert "PRIVATE_FAILURE_DETAIL" not in captions
    assert "Source body" not in captions
    assert events.path.read_bytes() == before
