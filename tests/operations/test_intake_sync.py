"""Synthetic transport has durable receipts and never claims live delivery."""

import sys

import pytest

from edn.operations.intake_sync import (
    SyntheticSyncError,
    SyntheticSyncStore,
    delivery_identity,
)


def payload():
    return {
        "request_id": "d411af59-c600-413b-a916-a462c395f108",
        "revision": 2,
        "content_hash": "a" * 64,
        "idempotency_key": "synthetic-submission-01",
        "approval": {"revision": 2, "content_hash": "a" * 64},
        "dry_run": True,
        "not_synced": True,
        "sync_status": "dry_run",
        "fields": {"Title": "Pending"},
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("revision", True),
        ("content_hash", "invalid"),
        ("not_synced", False),
        ("sync_status", "synced"),
        ("idempotency_key", "hidden\nkey"),
        ("approval", {"revision": 1}),
    ],
)
def test_delivery_rejects_unbound_or_live_success_input(key, value):
    candidate = payload()
    candidate[key] = value
    with pytest.raises(SyntheticSyncError):
        delivery_identity(candidate)


def test_identity_binds_exact_payload():
    original = delivery_identity(payload())
    changed = payload()
    changed["fields"] = {"Title": "changed"}
    assert delivery_identity(changed)["payload_hash"] != original["payload_hash"]


def store_or_refusal(tmp_path):
    root = tmp_path / "synthetic-sync"
    if sys.platform != "linux":
        with pytest.raises(ValueError, match="Linux"):
            SyntheticSyncStore(root)
        assert not root.exists()
        return None
    root.mkdir(mode=0o700)
    return SyntheticSyncStore(root)


def test_unknown_requires_reconciliation_and_survives_restart(tmp_path):
    store = store_or_refusal(tmp_path)
    if store is None:
        return
    result = store.deliver(payload(), "unknown")
    assert result["status"] == "unknown" and result["live_synced"] is False
    assert result["synthetic_id"] is None
    reopened = SyntheticSyncStore(store.root)
    with pytest.raises(SyntheticSyncError, match="Reconcile"):
        reopened.deliver(payload())
    resolved = reopened.reconcile(payload())
    assert resolved["status"] == "synced" and resolved["live_synced"] is False
    assert resolved["synthetic_id"].startswith("SYNTHETIC-")
    assert reopened.deliver(payload()) == resolved


def test_failed_attempt_can_retry_but_changed_payload_cannot(tmp_path):
    store = store_or_refusal(tmp_path)
    if store is None:
        return
    failed = store.deliver(payload(), "failed")
    assert failed["status"] == "failed" and failed["synthetic_id"] is None
    succeeded = store.deliver(payload(), "success")
    assert succeeded["status"] == "synced" and succeeded["attempt"] == 2
    changed = payload()
    changed["fields"] = {"Title": "changed"}
    with pytest.raises(SyntheticSyncError, match="does not match"):
        store.deliver(changed)
    assert store.get(payload()) == succeeded
