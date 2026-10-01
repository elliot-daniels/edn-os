import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from edn.operations.models import EVENT_TYPES, Event
from edn.operations.storage import EventStore


def event(**changes):
    return replace(
        Event(
            "outlook", "edn@example.com", "one", datetime.now(UTC), "inbound", "email"
        ),
        **changes,
    )


def test_replay_preserves_identity_content_and_account_isolation(tmp_path):
    path = tmp_path / "operations.db"
    store = EventStore(path)
    store.initialise()
    original = event(
        body="Source text",
        raw_payload={"id": "one"},
        attachments=({"name": "plan.pdf"},),
        parties=({"role": "from", "address": "client@example.com"},),
        ai_summary="Derived summary",
        ai_actions=("Review plan",),
    )
    assert store.insert(original).inserted
    replay = EventStore(path).insert(event(body="Changed"))
    assert not replay.inserted
    assert replay.event == original
    assert store.insert(event(source_account="other@example.com")).inserted
    assert len(store.list_events()) == 2


def test_newest_first_filters_and_read_only(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    old = event(occurred_at=datetime.now(UTC) - timedelta(days=1))
    new = event(
        external_id="two",
        source="website",
        needs_action=True,
        client_id="c1",
        project_id="p1",
        job_id="j1",
    )
    store.insert(old)
    store.insert(new)
    reader = EventStore(store.path, read_only=True)
    assert reader.list_events() == (new, old)
    assert reader.list_events(
        needs_action=True,
        source="website",
        client_id="c1",
        project_id="p1",
        job_id="j1",
    ) == (new,)
    assert reader.list_events(source="'; DROP TABLE operations_events;--") == ()
    assert reader.filter_values("client_id") == ("c1",)
    with pytest.raises(ValueError):
        reader.insert(new)
    with pytest.raises(ValueError):
        reader.initialise()


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
def test_all_operational_types_roundtrip(event_type):
    record = event(event_type=event_type)
    assert Event.from_dict(record.to_dict()) == record


def test_invalid_events_and_missing_database_do_not_create_store(tmp_path):
    for change in (
        {"external_id": ""},
        {"occurred_at": datetime(2026, 1, 1)},
        {"event_type": "unknown"},
        {"direction": "unknown"},
    ):
        with pytest.raises(ValueError):
            event(**change)
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        EventStore(path, read_only=True).list_events()
    assert not path.exists()
