import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest

from edn.operations.models import Event
from edn.operations.storage import EventStore

APP = Path(__file__).resolve().parents[2] / "src" / "edn" / "ui" / "app.py"


def test_operations_inbox_without_memory_and_filters(tmp_path, monkeypatch):
    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    store.insert(
        Event(
            "outlook",
            "edn@example.com",
            "m1",
            datetime.now(UTC),
            "inbound",
            "email",
            subject="Newest mail",
            body="<script>literal</script>",
            needs_action=True,
            client_id="c1",
            project_id="p1",
            job_id="j1",
        )
    )
    store.insert(
        Event(
            "website",
            "site",
            "r1",
            datetime.now(UTC) - timedelta(days=1),
            "inbound",
            "job_request",
            subject="Older request",
        )
    )
    monkeypatch.setenv("EDN_OPERATIONS_DB", str(path))
    monkeypatch.delenv("EDN_MEMORY_DB", raising=False)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    subjects = [item.value for item in app.text]
    assert subjects.index("Newest mail") < subjects.index("Older request")
    assert "<script>literal</script>" in subjects
    app.checkbox[0].check().run()
    assert "Older request" not in [item.value for item in app.text]
    app.checkbox[0].uncheck()
    app.selectbox[0].select("website").run()
    assert "Newest mail" not in [item.value for item in app.text]
    app.selectbox[0].select("All")
    app.selectbox[1].select("c1").run()
    assert "Newest mail" in [item.value for item in app.text]
    assert "Older request" not in [item.value for item in app.text]
    assert len(store.list_events()) == 2


def test_missing_configuration_and_empty_inbox(tmp_path, monkeypatch):
    monkeypatch.delenv("EDN_OPERATIONS_DB", raising=False)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception and app.info
    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    monkeypatch.setenv("EDN_OPERATIONS_DB", str(path))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert app.info[0].value == "No events match these filters."
    assert len(app.selectbox) == 1  # No fictional client/project/job catalogue.


def test_corrupt_attachment_metadata_fails_safely_without_writing(
    tmp_path, monkeypatch
):
    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    event = Event(
        "outlook", "edn@example.com", "m1", datetime.now(UTC), "inbound", "email"
    )
    store.insert(event)
    payload = event.to_dict()
    payload["attachments"] = [None]
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=?", (json.dumps(payload),)
        )
    before = path.read_bytes()
    monkeypatch.setenv("EDN_OPERATIONS_DB", str(path))
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert (
        app.error[0].value == "Operations database is unavailable or not initialized."
    )
    assert path.read_bytes() == before
