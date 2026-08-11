"""Durable bounded session references that cannot widen follow-up authority."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from edn.intelligence.models import AssembledContext, IntelligenceRequest

_SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_schema (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    principal_kind TEXT NOT NULL,
    delegated_by TEXT,
    active_domain_ids_json TEXT NOT NULL,
    purpose_id TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    classification_scheme_id TEXT NOT NULL,
    classification_level_id TEXT NOT NULL,
    resource_scope_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_evidence (
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL,
    tombstoned INTEGER NOT NULL CHECK(tombstoned IN (0, 1)),
    PRIMARY KEY(session_id, evidence_id)
);
"""


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: str
    principal_id: str
    tenant_id: str
    principal_kind: str
    delegated_by: str | None
    active_domain_ids: tuple[str, ...]
    purpose_id: str
    domain_id: str
    classification_id: tuple[str, str]
    resource_scope: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    tombstoned_evidence_ids: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, session_id: str, context: AssembledContext) -> SessionState:
        request = context.request
        principal = request.principal
        return cls(
            session_id,
            principal.principal_id,
            principal.tenant_id,
            principal.principal_kind,
            principal.delegated_by,
            tuple(sorted(domain.domain_id for domain in principal.active_domains)),
            request.purpose.purpose_id,
            request.security_domain.domain_id,
            (request.classification.scheme_id, request.classification.level_id),
            tuple(sorted(request.resource_scope)),
            tuple(item.context_id for item in context.evidence),
        )

    def authorizes(self, request: IntelligenceRequest) -> bool:
        principal = request.principal
        return self.authority_key == (
            principal.principal_id,
            principal.tenant_id,
            principal.principal_kind,
            principal.delegated_by,
            tuple(sorted(domain.domain_id for domain in principal.active_domains)),
            request.purpose.purpose_id,
            request.security_domain.domain_id,
            (request.classification.scheme_id, request.classification.level_id),
            tuple(sorted(request.resource_scope)),
        )

    @property
    def authority_key(
        self,
    ) -> tuple[
        str,
        str,
        str,
        str | None,
        tuple[str, ...],
        str,
        str,
        tuple[str, str],
        tuple[str, ...],
    ]:
        return (
            self.principal_id,
            self.tenant_id,
            self.principal_kind,
            self.delegated_by,
            self.active_domain_ids,
            self.purpose_id,
            self.domain_id,
            self.classification_id,
            self.resource_scope,
        )


class SessionStore(Protocol):
    def save(self, state: SessionState) -> None: ...

    def require_authorized(
        self, session_id: str, request: IntelligenceRequest
    ) -> SessionState: ...


def _reconcile(existing: SessionState | None, state: SessionState) -> SessionState:
    if existing is not None and existing.authority_key != state.authority_key:
        raise PermissionError("session authority boundary cannot be replaced")
    old_active = set(() if existing is None else existing.evidence_ids)
    old_tombstones = set(() if existing is None else existing.tombstoned_evidence_ids)
    new_active = set(state.evidence_ids)
    tombstones = (old_active - new_active) | (old_tombstones - new_active)
    return SessionState(
        state.session_id,
        state.principal_id,
        state.tenant_id,
        state.principal_kind,
        state.delegated_by,
        state.active_domain_ids,
        state.purpose_id,
        state.domain_id,
        state.classification_id,
        state.resource_scope,
        tuple(sorted(new_active)),
        tuple(sorted(tombstones)),
    )


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = _reconcile(
            self._sessions.get(state.session_id), state
        )

    def require_authorized(
        self, session_id: str, request: IntelligenceRequest
    ) -> SessionState:
        state = self.get(session_id)
        if state is None or not state.authorizes(request):
            raise PermissionError("follow-up requires the original authority boundary")
        return state


class SQLiteSessionStore:
    """SQLite reference store; no queries, excerpts, or transcript bodies persist."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialise(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            row = connection.execute(
                "SELECT version FROM session_schema WHERE component = 'sessions'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO session_schema(component, version) VALUES (?, ?)",
                    ("sessions", _SCHEMA_VERSION),
                )
            elif int(row["version"]) != _SCHEMA_VERSION:
                raise RuntimeError("unsupported Intelligence Core session schema")

    def _get(
        self, connection: sqlite3.Connection, session_id: str
    ) -> SessionState | None:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        evidence = connection.execute(
            """SELECT evidence_id, tombstoned FROM session_evidence
            WHERE session_id = ? ORDER BY evidence_id""",
            (session_id,),
        ).fetchall()
        return SessionState(
            str(row["session_id"]),
            str(row["principal_id"]),
            str(row["tenant_id"]),
            str(row["principal_kind"]),
            None if row["delegated_by"] is None else str(row["delegated_by"]),
            tuple(json.loads(str(row["active_domain_ids_json"]))),
            str(row["purpose_id"]),
            str(row["domain_id"]),
            (
                str(row["classification_scheme_id"]),
                str(row["classification_level_id"]),
            ),
            tuple(json.loads(str(row["resource_scope_json"]))),
            tuple(
                str(item["evidence_id"]) for item in evidence if not item["tombstoned"]
            ),
            tuple(str(item["evidence_id"]) for item in evidence if item["tombstoned"]),
        )

    def get(self, session_id: str) -> SessionState | None:
        with self._connect() as connection:
            return self._get(connection, session_id)

    def save(self, state: SessionState) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            reconciled = _reconcile(self._get(connection, state.session_id), state)
            connection.execute(
                """INSERT INTO sessions(
                    session_id, principal_id, tenant_id, principal_kind,
                    delegated_by, active_domain_ids_json, purpose_id, domain_id,
                    classification_scheme_id, classification_level_id,
                    resource_scope_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING""",
                (
                    reconciled.session_id,
                    reconciled.principal_id,
                    reconciled.tenant_id,
                    reconciled.principal_kind,
                    reconciled.delegated_by,
                    json.dumps(reconciled.active_domain_ids),
                    reconciled.purpose_id,
                    reconciled.domain_id,
                    *reconciled.classification_id,
                    json.dumps(reconciled.resource_scope),
                ),
            )
            connection.execute(
                "DELETE FROM session_evidence WHERE session_id = ?",
                (reconciled.session_id,),
            )
            connection.executemany(
                """INSERT INTO session_evidence(session_id, evidence_id, tombstoned)
                VALUES (?, ?, ?)""",
                (
                    (reconciled.session_id, evidence_id, tombstoned)
                    for tombstoned, identifiers in (
                        (0, reconciled.evidence_ids),
                        (1, reconciled.tombstoned_evidence_ids),
                    )
                    for evidence_id in identifiers
                ),
            )

    def require_authorized(
        self, session_id: str, request: IntelligenceRequest
    ) -> SessionState:
        state = self.get(session_id)
        if state is None or not state.authorizes(request):
            raise PermissionError("follow-up requires the original authority boundary")
        return state
