"""Metadata-only protected PA-009 envelope hygiene tests."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from edn.core import Classification
from edn.intelligence import (
    DisclosureProjection,
    FreshnessState,
    ModelRequest,
    PreflightReconciliationStatus,
    ProjectedEvidence,
    ProtectedPreflightStore,
    ProtectedProjectionEnvelope,
    TemporalState,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)


def _envelope(
    request_id: str,
    *,
    created_at: datetime = NOW,
    expires_at: datetime | None = None,
) -> ProtectedProjectionEnvelope:
    item = ProjectedEvidence(
        "disclosed-1",
        "Inbox",
        "Synthetic metadata",
        "Synthetic metadata only",
        FreshnessState.CURRENT,
        "synthetic-digest",
        NOW,
        "inbox.metadata",
        True,
        TemporalState.CURRENT_RECENT,
    )
    request = ModelRequest(
        request_id,
        "daily-intelligence",
        "owner",
        "EDN",
        ("disclosed-1",),
        DisclosureProjection(request_id, (item,), 42, reference_time=created_at),
        CLASSIFICATION,
        "model.summarize",
        5,
        synthetic_fixture=False,
    )
    return ProtectedProjectionEnvelope(
        request,
        hashlib.sha256(request_id.encode()).hexdigest(),
        "openai.api",
        "gpt-5-mini-2025-08-07",
        "openai-daily-brief-pilot-v1",
        "EDN",
        "confidential",
        ("inbox.metadata",),
        1,
        created_at,
        expires_at or created_at + timedelta(hours=1),
    )


def test_reconciliation_classifies_and_safely_resolves_all_states(
    tmp_path: Path,
) -> None:
    root = tmp_path / "provider-preflights"
    store = ProtectedPreflightStore(root)
    store.persist(_envelope("active-valid"))
    store.persist(
        _envelope(
            "expired-active",
            created_at=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(hours=1),
        )
    )
    store.persist(_envelope("claimed-in-flight"))
    claimed = store.claim("claimed-in-flight", now=NOW)
    assert claimed.request.request_id == "claimed-in-flight"
    store.persist(_envelope("terminal-orphan"))
    corrupt = root / f"{'f' * 64}.json"
    corrupt.write_text("not canonical json")
    corrupt.chmod(0o600)

    records = store.reconcile(
        terminal_request_ids=frozenset({"terminal-orphan"}), now=NOW
    )
    statuses = {record.request_id: record.status for record in records}

    assert statuses["active-valid"] is PreflightReconciliationStatus.ACTIVE_VALID
    assert statuses["expired-active"] is (
        PreflightReconciliationStatus.EXPIRED_REMOVED
    )
    assert statuses["claimed-in-flight"] is (
        PreflightReconciliationStatus.CLAIMED_IN_FLIGHT
    )
    assert statuses["terminal-orphan"] is (
        PreflightReconciliationStatus.TERMINAL_ORPHAN_REMOVED
    )
    assert any(
        record.status is PreflightReconciliationStatus.CORRUPT_UNKNOWN
        and record.request_id is None
        and not record.removed
        for record in records
    )
    assert store.exists("active-valid")
    assert not store.exists("expired-active")
    assert not store.exists("terminal-orphan")
    claimed_path = root / (
        f"{hashlib.sha256(b'claimed-in-flight').hexdigest()}.claimed"
    )
    assert claimed_path.exists()
    assert corrupt.exists()


def test_reconciliation_never_revives_or_dispatches_claims(tmp_path: Path) -> None:
    root = tmp_path / "provider-preflights"
    store = ProtectedPreflightStore(root)
    store.persist(_envelope("terminal-claimed"))
    store.claim("terminal-claimed", now=NOW)

    records = store.reconcile(
        terminal_request_ids=frozenset({"terminal-claimed"}), now=NOW
    )

    assert records[0].status is PreflightReconciliationStatus.TERMINAL_ORPHAN_REMOVED
    assert records[0].claimed is True
    assert records[0].removed is True
    assert not store.exists("terminal-claimed")
    assert not (
        root / f"{hashlib.sha256(b'terminal-claimed').hexdigest()}.claimed"
    ).exists()
    assert not hasattr(store, "dispatch")


def test_corrupt_or_unsafe_envelopes_remain_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "provider-preflights"
    store = ProtectedPreflightStore(root)
    store.persist(_envelope("unsafe-mode"))
    path = root / f"{hashlib.sha256(b'unsafe-mode').hexdigest()}.json"
    os.chmod(path, 0o644)

    records = store.reconcile(now=NOW)

    assert records[0].status is PreflightReconciliationStatus.CORRUPT_UNKNOWN
    assert records[0].removed is False
    assert path.exists()
