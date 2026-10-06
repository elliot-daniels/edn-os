"""Explicit transactional Operations schema initialization and legacy migration."""

from __future__ import annotations

import json
import sqlite3

from edn.operations.models import Event

SCHEMA_VERSION = 1
EVENT_COLUMNS = (
    "id",
    "source",
    "source_account",
    "external_id",
    "occurred_at",
    "needs_action",
    "client_id",
    "project_id",
    "job_id",
    "payload",
)
IDENTITY_COLUMNS = ("identity_key", "event_id")

EVENT_DDL = """CREATE TABLE operations_events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_account TEXT NOT NULL,
    external_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    needs_action INTEGER NOT NULL,
    client_id TEXT,
    project_id TEXT,
    job_id TEXT,
    payload TEXT NOT NULL,
    UNIQUE(source, source_account, external_id)
)"""


class UnsupportedEventSchemaError(ValueError):
    """Store is incompatible; no automatic read/write/upgrade is authorized."""


def schema_version(connection: sqlite3.Connection) -> int:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version not in {0, SCHEMA_VERSION}:
        raise UnsupportedEventSchemaError("Unsupported Operations Event schema version")
    return version


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    # Only fixed internal table identifiers enter SQL.
    return tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))


def _validate_event_constraints(connection: sqlite3.Connection) -> None:
    columns = connection.execute("PRAGMA table_info(operations_events)").fetchall()
    required = {
        "source",
        "source_account",
        "external_id",
        "occurred_at",
        "needs_action",
        "payload",
    }
    for column in columns:
        expected_type = "INTEGER" if column[1] == "needs_action" else "TEXT"
        if (
            column[2].upper() != expected_type
            or column[3] != int(column[1] in required)
            or column[5] != int(column[1] == "id")
        ):
            raise UnsupportedEventSchemaError(
                "Event column constraints are incompatible"
            )
    indexes = connection.execute("PRAGMA index_list(operations_events)").fetchall()
    if not any(
        index[2] == 1
        and index[4] == 0
        and tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (index[1],)
            )
        )
        == ("source", "source_account", "external_id")
        for index in indexes
    ):
        raise UnsupportedEventSchemaError(
            "Event replay uniqueness constraint is missing"
        )


def validate_schema(connection: sqlite3.Connection, *, read_only: bool) -> None:
    version = schema_version(connection)
    if _columns(connection, "operations_events") != EVENT_COLUMNS:
        raise UnsupportedEventSchemaError(
            "Operations Event table has incompatible columns"
        )
    _validate_event_constraints(connection)
    if version == 0:
        if not read_only:
            raise UnsupportedEventSchemaError(
                "Explicit initialise is required for legacy Events"
            )
        return
    if _columns(connection, "operations_event_identities") != IDENTITY_COLUMNS:
        raise UnsupportedEventSchemaError(
            "Operations identity table is missing or incompatible"
        )
    identity_columns = connection.execute(
        "PRAGMA table_info(operations_event_identities)"
    ).fetchall()
    if tuple((row[2].upper(), row[3], row[5]) for row in identity_columns) != (
        ("TEXT", 1, 1),
        ("TEXT", 1, 0),
    ):
        raise UnsupportedEventSchemaError(
            "Operations identity constraints are incompatible"
        )
    foreign_keys = connection.execute(
        "PRAGMA foreign_key_list(operations_event_identities)"
    ).fetchall()
    if len(foreign_keys) != 1 or foreign_keys[0][2:5] != (
        "operations_events",
        "event_id",
        "id",
    ):
        raise UnsupportedEventSchemaError(
            "Operations identity reference is incompatible"
        )
    identity_indexes = connection.execute(
        "PRAGMA index_list(operations_event_identities)"
    ).fetchall()
    if not any(
        index[2] == 1
        and index[4] == 0
        and tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM pragma_index_info(?) ORDER BY seqno", (index[1],)
            )
        )
        == ("event_id",)
        for index in identity_indexes
    ):
        raise UnsupportedEventSchemaError(
            "Operations identity references must be unique"
        )


def initialise_schema(connection: sqlite3.Connection) -> None:
    """Backfill identities and publish version only in one successful transaction."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = schema_version(connection)
        columns = _columns(connection, "operations_events")
        if version == SCHEMA_VERSION:
            validate_schema(connection, read_only=False)
            connection.commit()
            return
        if columns:
            if columns != EVENT_COLUMNS:
                raise UnsupportedEventSchemaError(
                    "Legacy Event table has incompatible columns"
                )
            _validate_event_constraints(connection)
        else:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables - {"operations_import_outcomes"}:
                raise UnsupportedEventSchemaError(
                    "Database is not an Operations Event store"
                )
            connection.execute(EVENT_DDL)
        if _columns(connection, "operations_event_identities"):
            raise UnsupportedEventSchemaError(
                "Unversioned identity table cannot be adopted"
            )
        connection.execute("""CREATE TABLE operations_event_identities (
            identity_key TEXT PRIMARY KEY NOT NULL,
            event_id TEXT NOT NULL UNIQUE REFERENCES operations_events(id)
        )""")
        rows = connection.execute("SELECT * FROM operations_events")
        for row in rows:
            local_id, source, account, external_id = row[:4]
            payload = row[9]
            try:
                event = Event.from_dict(json.loads(payload))
            except (
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
                RecursionError,
            ) as error:
                raise UnsupportedEventSchemaError(
                    "Legacy Event payload cannot be migrated"
                ) from error
            if (event.id, event.source, event.source_account, event.external_id) != (
                local_id,
                source,
                account,
                external_id,
            ):
                raise UnsupportedEventSchemaError(
                    "Legacy Event provenance does not match stored identity"
                )
            if row[4:9] != (
                event.to_dict()["occurred_at"],
                int(event.needs_action),
                event.client_id,
                event.project_id,
                event.job_id,
            ):
                raise UnsupportedEventSchemaError(
                    "Legacy Event index fields do not match payload"
                )
            connection.execute(
                "INSERT INTO operations_event_identities VALUES (?, ?)",
                (event.identity_key, local_id),
            )
        connection.execute("""CREATE INDEX IF NOT EXISTS operations_events_newest
            ON operations_events(occurred_at DESC, id DESC)""")
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
