"""Synthetic explicit schema upgrade and source-identity preservation tests."""

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from edn.operations.models import Event, event_identity_key
from edn.operations.schema import EVENT_DDL, UnsupportedEventSchemaError
from edn.operations.storage import EventStore


def event(**changes):
    return replace(
        Event(
            "outlook",
            "test@example.com",
            "source-one",
            datetime(2026, 10, 6, tzinfo=UTC),
            "inbound",
            "email",
        ),
        **changes,
    )


def legacy(path, *records):
    with sqlite3.connect(path) as connection:
        connection.execute(EVENT_DDL)
        for record in records:
            connection.execute(
                "INSERT INTO operations_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.source,
                    record.source_account,
                    record.external_id,
                    record.to_dict()["occurred_at"],
                    int(record.needs_action),
                    record.client_id,
                    record.project_id,
                    record.job_id,
                    json.dumps(record.to_dict()),
                ),
            )


def snapshot(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.iterdump())


def test_identity_is_deterministic_without_conflating_source_or_accounts():
    original = event(body="original")
    retry = event(body="changed", needs_action=True)
    assert original.id != retry.id
    assert original.identity_key == retry.identity_key
    assert original.identity_key.startswith("event-source-v1:")
    for changes in (
        {"source": "website"},
        {"source_account": "other@example.com"},
        {"external_id": "source-two"},
        {"external_id": "SOURCE-ONE"},
    ):
        assert replace(original, **changes).identity_key != original.identity_key
    assert event_identity_key("a:b", "c", "d") != event_identity_key("a", "b:c", "d")
    assert event_identity_key("source", "a@EXAMPLE.com", "one") != event_identity_key(
        "source", "a@example.com", "one"
    )


@pytest.mark.parametrize("value", ["", " ", None, 1])
def test_identity_rejects_invalid_source_components(value):
    with pytest.raises(ValueError):
        event_identity_key("source", "account", value)


def test_explicit_migration_preserves_existing_rows_ids_and_first_write(tmp_path):
    path = tmp_path / "legacy.db"
    original = event(body="first source payload", id="existing-local-uuid")
    legacy(path, original)
    before = EventStore(path, read_only=True).list_events()
    assert before == (original,)
    with pytest.raises(UnsupportedEventSchemaError, match="initialise"):
        EventStore(path).insert(event())
    store = EventStore(path)
    store.initialise()
    assert store.list_events() == before
    replay = store.insert(event(body="changed source content"))
    assert replay.event == original
    assert not replay.inserted
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT * FROM operations_event_identities"
        ).fetchall() == [(original.identity_key, original.id)]
    after = snapshot(path)
    store.initialise()
    assert snapshot(path) == after


def test_new_store_persists_same_identity_across_independent_databases(tmp_path):
    records = []
    keys = []
    for name in ("first.db", "second.db"):
        store = EventStore(tmp_path / name)
        store.initialise()
        record = event()
        records.append(store.insert(record).event)
        with sqlite3.connect(store.path) as connection:
            keys.append(
                connection.execute(
                    "SELECT identity_key FROM operations_event_identities"
                ).fetchone()[0]
            )
    assert records[0].id != records[1].id
    assert keys[0] == keys[1] == records[0].identity_key


@pytest.mark.parametrize(
    "mutation", ["payload_identity", "physical_identity", "bad_payload"]
)
def test_failed_legacy_migration_rolls_back_data_schema_and_version(tmp_path, mutation):
    path = tmp_path / "legacy.db"
    original = event()
    legacy(path, event(external_id="valid-first"), original)
    with sqlite3.connect(path) as connection:
        if mutation == "physical_identity":
            connection.execute(
                "UPDATE operations_events SET source_account='other' WHERE id=?",
                (original.id,),
            )
        elif mutation == "bad_payload":
            connection.execute(
                "UPDATE operations_events SET payload='not-json' WHERE id=?",
                (original.id,),
            )
        else:
            payload = original.to_dict() | {"external_id": "changed"}
            connection.execute(
                "UPDATE operations_events SET payload=? WHERE id=?",
                (json.dumps(payload), original.id),
            )
    before = snapshot(path)
    with pytest.raises(UnsupportedEventSchemaError):
        EventStore(path).initialise()
    assert snapshot(path) == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name='operations_event_identities'"
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("operation", ["initialise", "insert", "list", "filters"])
def test_future_schema_is_rejected_without_data_or_version_changes(tmp_path, operation):
    path = tmp_path / "future.db"
    store = EventStore(path)
    store.initialise()
    store.insert(event())
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=999")
    before = snapshot(path)
    actions = {
        "initialise": store.initialise,
        "insert": lambda: store.insert(event()),
        "list": lambda: EventStore(path, read_only=True).list_events(),
        "filters": lambda: EventStore(path, read_only=True).filter_values("source"),
    }
    with pytest.raises(UnsupportedEventSchemaError, match="version"):
        actions[operation]()
    assert snapshot(path) == before


def test_identity_constraint_failure_rolls_back_event_insert(tmp_path):
    path = tmp_path / "events.db"
    store = EventStore(path)
    store.initialise()
    first = event()
    store.insert(first)
    second = event(external_id="another")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE operations_event_identities SET identity_key=?",
            (second.identity_key,),
        )
    before = snapshot(path)
    with pytest.raises(ValueError, match="inconsistent"):
        store.insert(second)
    assert snapshot(path) == before


def test_incompatible_legacy_columns_and_unrelated_db_are_not_adopted(tmp_path):
    for ddl in (
        "CREATE TABLE operations_events (id TEXT)",
        "CREATE TABLE unrelated (id TEXT)",
    ):
        path = tmp_path / str(len(ddl))
        with sqlite3.connect(path) as connection:
            connection.execute(ddl)
        before = snapshot(path)
        with pytest.raises(UnsupportedEventSchemaError):
            EventStore(path).initialise()
        assert snapshot(path) == before


def test_incompatible_legacy_replay_constraint_is_rejected(tmp_path):
    path = tmp_path / "missing-constraint.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            EVENT_DDL.replace(",\n    UNIQUE(source, source_account, external_id)", "")
        )
    before = snapshot(path)
    with pytest.raises(UnsupportedEventSchemaError, match="uniqueness"):
        EventStore(path).initialise()
    assert snapshot(path) == before


def test_legacy_projection_mismatch_rolls_back_upgrade(tmp_path):
    path = tmp_path / "mismatched.db"
    legacy(path, event())
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE operations_events SET needs_action=1")
    before = snapshot(path)
    with pytest.raises(UnsupportedEventSchemaError, match="index fields"):
        EventStore(path).initialise()
    assert snapshot(path) == before


def test_concurrent_replay_has_one_event_and_one_durable_identity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "concurrent.db"
    EventStore(path).initialise()
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(lambda i: EventStore(path).insert(event(body=str(i))), range(8))
        )
    assert sum(result.inserted for result in results) == 1
    assert len({result.event.id for result in results}) == 1
    assert len({result.event.identity_key for result in results}) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM operations_events"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM operations_event_identities"
        ).fetchone() == (1,)


def test_read_only_legacy_access_never_updates_schema(tmp_path):
    path = tmp_path / "readonly.db"
    legacy(path, event())
    before = snapshot(path)
    reader = EventStore(path, read_only=True)
    assert len(reader.list_events()) == 1
    assert reader.filter_values("source") == ("outlook",)
    with pytest.raises(ValueError, match="Read-only"):
        reader.initialise()
    assert snapshot(path) == before


def test_current_version_with_missing_identity_table_is_rejected(tmp_path):
    path = tmp_path / "broken-current.db"
    legacy(path, event())
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=1")
    before = snapshot(path)
    for reader in (EventStore(path), EventStore(path, read_only=True)):
        with pytest.raises(UnsupportedEventSchemaError, match="identity table"):
            reader.list_events()
    with pytest.raises(UnsupportedEventSchemaError, match="identity table"):
        EventStore(path).initialise()
    assert snapshot(path) == before


def test_current_identity_registry_requires_unique_event_references(tmp_path):
    path = tmp_path / "lookalike.db"
    legacy(path, event())
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE operations_event_identities (
            identity_key TEXT PRIMARY KEY NOT NULL,
            event_id TEXT NOT NULL REFERENCES operations_events(id)
        )""")
        connection.execute("PRAGMA user_version=1")
    before = snapshot(path)
    for action in (
        lambda: EventStore(path).initialise(),
        lambda: EventStore(path).insert(event()),
        lambda: EventStore(path, read_only=True).list_events(),
    ):
        with pytest.raises(UnsupportedEventSchemaError, match="unique"):
            action()
    assert snapshot(path) == before


def test_deep_json_migration_returns_safe_error_and_rolls_back(tmp_path):
    path = tmp_path / "deep.db"
    legacy(path, event(external_id="first"), event())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=? WHERE external_id=?",
            ("[" * 10000 + "0" + "]" * 10000, "source-one"),
        )
    before = snapshot(path)
    with pytest.raises(UnsupportedEventSchemaError, match="cannot be migrated"):
        EventStore(path).initialise()
    assert snapshot(path) == before


@pytest.mark.parametrize("field", ["id", "source", "source_account", "external_id"])
def test_corrupt_replay_payload_identity_never_updates_registry(tmp_path, field):
    path = tmp_path / "corrupt-replay.db"
    store = EventStore(path)
    store.initialise()
    original = event()
    store.insert(original)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=?",
            (json.dumps(original.to_dict() | {field: "changed"}),),
        )
    before = snapshot(path)
    with pytest.raises(ValueError, match="provenance"):
        store.insert(event(body="replayed content"))
    assert snapshot(path) == before
