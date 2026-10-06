"""Isolated SQLite Event store, first-write-wins with durable replay protection."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from edn.operations.models import Event
from edn.operations.schema import initialise_schema, validate_schema


@dataclass(frozen=True)
class InsertResult:
    event: Event
    inserted: bool


class EventStore:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self.read_only = read_only

    def _connect(self) -> sqlite3.Connection:
        mode = "ro" if self.read_only else "rw"
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode={mode}", uri=True
        )
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            validate_schema(connection, read_only=self.read_only)
        except BaseException:
            connection.close()
            raise
        return connection

    def initialise(self) -> None:
        if self.read_only:
            raise ValueError("Read-only Event store cannot initialise")
        # Parent must already exist; caller selects an approved runtime path.
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            initialise_schema(connection)

    def insert(self, event: Event) -> InsertResult:
        if self.read_only:
            raise ValueError("Read-only Event store cannot insert")
        payload = json.dumps(event.to_dict(), sort_keys=True, ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO operations_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_account, external_id) DO NOTHING""",
                (
                    event.id,
                    event.source,
                    event.source_account,
                    event.external_id,
                    event.to_dict()["occurred_at"],
                    int(event.needs_action),
                    event.client_id,
                    event.project_id,
                    event.job_id,
                    payload,
                ),
            )
            row = connection.execute(
                """SELECT id, source, source_account, external_id, payload
                FROM operations_events
                WHERE source=? AND source_account=? AND external_id=?""",
                (event.source, event.source_account, event.external_id),
            ).fetchone()
            assert row is not None
            stored = Event.from_dict(json.loads(row[4]))
            if (
                stored.id,
                stored.source,
                stored.source_account,
                stored.external_id,
            ) != row[:4]:
                raise ValueError(
                    "Stored Event provenance does not match physical identity"
                )
            connection.execute(
                "INSERT INTO operations_event_identities VALUES (?, ?) "
                "ON CONFLICT(identity_key) DO NOTHING",
                (stored.identity_key, stored.id),
            )
            identity = connection.execute(
                "SELECT event_id FROM operations_event_identities WHERE identity_key=?",
                (stored.identity_key,),
            ).fetchone()
            if identity != (stored.id,):
                raise ValueError("Stored Event identity mapping is inconsistent")
            return InsertResult(stored, cursor.rowcount == 1)

    def list_events(
        self,
        *,
        needs_action: bool = False,
        source: str | None = None,
        client_id: str | None = None,
        project_id: str | None = None,
        job_id: str | None = None,
        limit: int = 100,
    ) -> tuple[Event, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("Event list limit must be between 1 and 500")
        clauses: list[str] = []
        parameters: list[str | int] = []
        if needs_action:
            clauses.append("needs_action=1")
        for name, value in (
            ("source", source),
            ("client_id", client_id),
            ("project_id", project_id),
            ("job_id", job_id),
        ):
            if value is not None:
                clauses.append(f"{name}=?")
                parameters.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM operations_events"
                + where
                + " ORDER BY occurred_at DESC, id DESC LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(Event.from_dict(json.loads(row[0])) for row in rows)

    def filter_values(self, field: str) -> tuple[str, ...]:
        if field not in {"source", "client_id", "project_id", "job_id"}:
            raise ValueError("Unsupported filter field")
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT {field} FROM operations_events "
                f"WHERE {field} IS NOT NULL ORDER BY {field}"
            ).fetchall()
        return tuple(row[0] for row in rows)
