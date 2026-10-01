"""IC-011 durable authority-bound session reference tests."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest
from tests.intelligence.test_context_alpha import (
    CLASSIFICATION,
    EDN,
    PERSONAL,
    PURPOSE,
    _request,
)

from edn.core import PrincipalContext
from edn.intelligence import SessionState, SQLiteSessionStore


def _state(
    *,
    session_id: str = "session-1",
    evidence_ids: tuple[str, ...] = ("evidence-1", "evidence-2"),
) -> SessionState:
    return SessionState(
        session_id,
        "elliot",
        "tenant",
        "person",
        None,
        (EDN.domain_id,),
        PURPOSE.purpose_id,
        EDN.domain_id,
        (CLASSIFICATION.scheme_id, CLASSIFICATION.level_id),
        (),
        evidence_ids,
    )


def test_restart_preserves_only_authority_and_evidence_references(tmp_path) -> None:
    path = tmp_path / "sessions.db"
    store = SQLiteSessionStore(path)
    store.initialise()
    store.save(_state())

    restarted = SQLiteSessionStore(path)
    loaded = restarted.require_authorized("session-1", _request())

    assert loaded == _state()
    with sqlite3.connect(path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
    assert {"query", "transcript", "excerpt"}.isdisjoint(columns)


def test_follow_up_cannot_widen_authority_boundary(tmp_path) -> None:
    store = SQLiteSessionStore(tmp_path / "sessions.db")
    store.initialise()
    store.save(_state())

    broader_principal = PrincipalContext(
        "elliot", "tenant", frozenset({EDN, PERSONAL}), True
    )
    broader_request = replace(_request(), principal=broader_principal)
    scoped_request = replace(_request(), resource_scope=("additional-scope",))

    with pytest.raises(PermissionError, match="original authority"):
        store.require_authorized("session-1", broader_request)
    with pytest.raises(PermissionError, match="original authority"):
        store.require_authorized("session-1", scoped_request)
    with pytest.raises(PermissionError, match="original authority"):
        store.require_authorized("session-1", _request(PERSONAL))
    with pytest.raises(PermissionError, match="cannot be replaced"):
        store.save(replace(_state(), purpose_id="other-purpose"))


def test_removed_evidence_is_tombstoned_and_not_returned_as_active(tmp_path) -> None:
    path = tmp_path / "sessions.db"
    store = SQLiteSessionStore(path)
    store.initialise()
    store.save(_state())
    store.save(_state(evidence_ids=("evidence-2",)))

    restarted = SQLiteSessionStore(path)
    loaded = restarted.require_authorized("session-1", _request())

    assert loaded.evidence_ids == ("evidence-2",)
    assert loaded.tombstoned_evidence_ids == ("evidence-1",)


def test_reauthorised_evidence_can_leave_tombstone_state(tmp_path) -> None:
    store = SQLiteSessionStore(tmp_path / "sessions.db")
    store.initialise()
    store.save(_state())
    store.save(_state(evidence_ids=("evidence-2",)))
    store.save(_state())

    loaded = store.require_authorized("session-1", _request())

    assert loaded.evidence_ids == ("evidence-1", "evidence-2")
    assert loaded.tombstoned_evidence_ids == ()
