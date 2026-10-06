"""Malformed synthetic legacy data stays private and unchanged on rejection."""

import json
import sqlite3
import traceback

import pytest

from edn.operations.cli import main
from edn.operations.schema import UnsupportedEventSchemaError
from edn.operations.storage import EventStore
from tests.operations.test_schema import event, legacy

SECRET = "synthetic-source-private-marker"


def malformed_payload(kind, record):
    payload = record.to_dict()
    if kind == "json":
        return SECRET + "{"
    if kind == "bytes":
        return SECRET.encode() + b"\xff"
    if kind == "recursion":
        return "[" * 10000 + "0" + "]" * 10000
    if kind == "container":
        return json.dumps([SECRET])
    if kind == "timestamp":
        return json.dumps(payload | {"occurred_at": SECRET})
    if kind == "metadata_type":
        return json.dumps(payload | {"attachments": SECRET})
    return json.dumps(payload)


def snapshot(path):
    with sqlite3.connect(path) as connection:
        return (
            connection.execute("PRAGMA user_version").fetchone(),
            connection.execute("SELECT * FROM sqlite_master ORDER BY name").fetchall(),
            connection.execute(
                "SELECT * FROM operations_events ORDER BY rowid"
            ).fetchall(),
        )


def prepare(path, kind):
    valid = event(external_id="valid-neighbor", body=SECRET)
    invalid = event(external_id="invalid-neighbor")
    legacy(path, valid, invalid)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE operations_events SET payload=? WHERE id=?",
            (malformed_payload(kind, invalid), invalid.id),
        )
        if kind == "index":
            connection.execute(
                "UPDATE operations_events SET needs_action=1 WHERE id=?",
                (invalid.id,),
            )
    return valid


@pytest.mark.parametrize(
    "kind",
    [
        "json",
        "bytes",
        "recursion",
        "container",
        "timestamp",
        "metadata_type",
        "index",
    ],
)
def test_rejected_migration_has_fixed_diagnostic_and_rolls_back_neighbors(
    tmp_path, kind
):
    path = tmp_path / "legacy.db"
    prepare(path, kind)
    before = snapshot(path)
    before_bytes = path.read_bytes()
    with pytest.raises(UnsupportedEventSchemaError) as raised:
        EventStore(path).initialise()
    diagnostic = "".join(traceback.format_exception(raised.value))
    assert SECRET not in diagnostic
    assert "UnicodeDecodeError" not in diagnostic
    assert "JSONDecodeError" not in diagnostic
    assert "RecursionError" not in diagnostic
    assert str(raised.value) in {
        "Legacy Event payload cannot be migrated",
        "Legacy Event index fields do not match payload",
    }
    assert snapshot(path) == before
    assert path.read_bytes() == before_bytes
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name='operations_event_identities'"
            ).fetchone()
            is None
        )


def test_valid_legacy_neighbors_migrate_without_changing_source_rows(tmp_path):
    path = tmp_path / "legacy.db"
    records = (event(external_id="one", body=SECRET), event(external_id="two"))
    legacy(path, *records)
    before_rows = snapshot(path)[2]
    EventStore(path).initialise()
    assert snapshot(path)[2] == before_rows
    assert EventStore(path, read_only=True).list_events() == tuple(
        sorted(
            records, key=lambda record: (record.occurred_at, record.id), reverse=True
        )
    )
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM operations_event_identities"
        ).fetchone() == (2,)


def test_public_init_command_rejects_without_source_details_or_mutation(
    tmp_path, capsys
):
    path = tmp_path / "legacy.db"
    prepare(path, "timestamp")
    before = snapshot(path)
    with pytest.raises(SystemExit) as raised:
        main(["init", "--database", str(path), "--data-root", str(tmp_path)])
    assert raised.value.code == 2
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert "Legacy Event payload cannot be migrated" in output.err
    assert snapshot(path) == before
