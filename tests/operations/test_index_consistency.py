"""Selection and rendering must describe the same immutable source snapshot."""

import json
import sqlite3

import pytest

from edn.operations.storage import EventStore
from tests.operations.test_malformed_events import example


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "other-id"),
        ("source", "other-source"),
        ("source_account", "other@example.com"),
        ("external_id", "other-record"),
        ("occurred_at", "2026-01-01T00:00:00+00:00"),
        ("needs_action", 1),
        ("client_id", "other-client"),
        ("project_id", "other-project"),
        ("job_id", "other-job"),
    ],
)
def test_mismatched_index_rows_are_isolated_without_rewriting(tmp_path, field, value):
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    valid, corrupt = example("valid"), example("corrupt")
    store.insert(valid)
    store.insert(corrupt)
    payload = corrupt.to_dict()
    payload[field] = bool(value) if field == "needs_action" else value
    # Alter only JSON; physical indexes and identity constraints remain intact.
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=? WHERE id=?",
            (json.dumps(payload), corrupt.id),
        )
    before = store.path.read_bytes()
    reader = EventStore(store.path, read_only=True)
    result = reader.list_events_with_diagnostics()
    assert result.events == (valid,) and result.malformed == 1
    bounded = reader.list_events_with_diagnostics(limit=1)
    assert len(bounded.events) + bounded.malformed == 1
    with pytest.raises(ValueError):
        reader.list_events()
    with pytest.raises(ValueError):
        store.insert(corrupt)
    assert store.path.read_bytes() == before


def test_filtered_inbox_never_renders_another_snapshot(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    store = EventStore(tmp_path / "events.db")
    store.initialise()
    corrupt = example("corrupt")
    store.insert(corrupt)
    payload = corrupt.to_dict() | {"source": "other", "subject": "PRIVATE SNAPSHOT"}
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
    app.selectbox[0].select("outlook").run()
    assert not app.exception and not app.error
    assert "1 malformed event(s)" in app.warning[0].value
    assert "PRIVATE SNAPSHOT" not in [item.value for item in app.text]
    assert store.path.read_bytes() == before


def test_valid_physical_filter_matches_snapshot(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    event = example()
    store.insert(event)
    assert store.list_events(source="outlook") == (event,)
    assert store.list_events(source="other") == ()
