import json
import sqlite3
from datetime import UTC, datetime

import pytest

from edn.operations.models import Event
from edn.operations.storage import EventStore


def example(identifier="valid"):
    return Event(
        "outlook",
        "test@example.com",
        identifier,
        datetime.now(UTC),
        "inbound",
        "email",
        subject="Valid activity",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"source": None},
        {"id": []},
        {"occurred_at": None},
        {"created_at": 3},
        {"event_type": []},
        {"direction": {}},
        {"parties": [None]},
        {"parties": [{"address": {}}]},
        {"parties": "text"},
        {"ai_actions": [None]},
        {"ai_actions": "text"},
        {"subject": []},
        {"body": None},
        {"needs_action": "false"},
        {"raw_payload": []},
        {"ai_summary": {}},
        {"client_id": []},
        {"unexpected": "field"},
    ],
)
def test_invalid_payloads_raise_value_error(change):
    payload = example().to_dict()
    payload.update(change)
    with pytest.raises(ValueError):
        Event.from_dict(payload)


@pytest.mark.parametrize("payload", [None, [], "text", {}, {"attachments": []}])
def test_nonobjects_and_missing_fields_rejected(payload):
    with pytest.raises(ValueError):
        Event.from_dict(payload)


def test_bounded_resilient_read_preserves_rows_and_reports_omissions(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    valid = example()
    corrupt = example("corrupt")
    store.insert(valid)
    store.insert(corrupt)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=? WHERE id=?",
            ("not JSON", corrupt.id),
        )
    before = store.path.read_bytes()
    reader = EventStore(store.path, read_only=True)
    result = reader.list_events_with_diagnostics()
    assert result.events == (valid,)
    assert result.malformed == 1
    limited = reader.list_events_with_diagnostics(limit=1)
    assert len(limited.events) + limited.malformed == 1
    with pytest.raises(ValueError):
        reader.list_events()
    assert store.path.read_bytes() == before


def test_schema_and_database_errors_are_not_swallowed(tmp_path):
    path = tmp_path / "wrong.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
    with pytest.raises(sqlite3.OperationalError):
        EventStore(path, read_only=True).list_events_with_diagnostics()


def test_deep_json_does_not_hide_valid_neighbors(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    valid = example()
    corrupt = example("deep")
    store.insert(valid)
    store.insert(corrupt)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=? WHERE id=?",
            ("[" * 10000 + "0" + "]" * 10000, corrupt.id),
        )
    before = store.path.read_bytes()
    reader = EventStore(store.path, read_only=True)
    result = reader.list_events_with_diagnostics()
    assert result.events == (valid,) and result.malformed == 1
    assert store.path.read_bytes() == before


def test_valid_neighbors_render_without_corrupt_content(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    store = EventStore(tmp_path / "events.db")
    store.initialise()
    store.insert(example())
    corrupt = example("corrupt")
    store.insert(corrupt)
    payload = corrupt.to_dict()
    payload["parties"] = ["PRIVATE INVALID CONTENT"]
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=? WHERE id=?",
            (json.dumps(payload), corrupt.id),
        )
    before = store.path.read_bytes()
    monkeypatch.setenv("EDN_OPERATIONS_DB", str(store.path))
    app = AppTest.from_string(
        "from edn.ui.operations import render_operations_inbox\n"
        "render_operations_inbox()"
    ).run()
    assert not app.exception and not app.error
    assert "Valid activity" in [item.value for item in app.text]
    assert "1 malformed event(s)" in app.warning[0].value
    assert "PRIVATE" not in app.warning[0].value
    assert store.path.read_bytes() == before
