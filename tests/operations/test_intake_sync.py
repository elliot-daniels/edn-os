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


def test_recursive_payload_has_fixed_failure():
    candidate = payload()
    nested = {}
    nested["self"] = nested
    candidate["fields"] = nested
    with pytest.raises(SyntheticSyncError):
        delivery_identity(candidate)


@pytest.mark.parametrize(
    "mutation", ["list_status", "extra", "bool_revision", "bad_time"]
)
def test_stored_receipt_corruption_has_fixed_error(mutation):
    identity = delivery_identity(payload())
    receipt = {
        "identity": dict(identity),
        "status": "pending",
        "mode": "synthetic",
        "live_synced": False,
        "attempt": 1,
        "actor": "local operator, uid=1000",
        "timestamp": "2026-10-09T00:00:00+00:00",
        "synthetic_id": None,
    }
    if mutation == "list_status":
        receipt["status"] = []
    elif mutation == "extra":
        receipt["private-source"] = "PRIVATE-SECRET"
    elif mutation == "bool_revision":
        identity["revision"] = 1
        receipt["identity"]["revision"] = True
    else:
        receipt["timestamp"] = "PRIVATE-SECRET"
    with pytest.raises(SyntheticSyncError) as error:
        SyntheticSyncStore._validate(receipt, identity)
    assert "PRIVATE-SECRET" not in str(error.value)


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


def test_tampered_success_receipt_requires_ledger_confirmation(tmp_path):
    store = store_or_refusal(tmp_path)
    if store is None:
        return
    import json

    original = store.deliver(payload())
    path = next(store.root.glob("*.receipt.json"))
    tampered = dict(original)
    tampered["synthetic_id"] = "SYNTHETIC-d411af59-c600-413b-a916-a462c395f108"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    for action in (store.get, store.deliver):
        with pytest.raises(SyntheticSyncError, match="inconsistent"):
            action(payload())
    assert store.reconcile(payload())["synthetic_id"] == original["synthetic_id"]


def test_missing_success_ledger_never_claims_confirmation_or_allows_retry(tmp_path):
    store = store_or_refusal(tmp_path)
    if store is None:
        return
    store.deliver(payload())
    receipt = next(store.root.glob("*.receipt.json"))
    before = receipt.read_bytes()
    next(store.root.glob("*.ledger.json")).unlink()
    for action in (store.get, store.deliver, store.reconcile):
        with pytest.raises(SyntheticSyncError):
            action(payload())
    assert receipt.read_bytes() == before


@pytest.mark.parametrize(
    "phase",
    [
        "before_pending",
        "after_pending",
        "before_ledger",
        "after_ledger",
        "before_final",
        "after_final",
    ],
)
def test_interrupted_publication_restarts_without_duplicate_delivery(
    tmp_path, monkeypatch, phase
):
    store = store_or_refusal(tmp_path)
    if store is None:
        return
    actual_write = SyntheticSyncStore._write

    def interrupted(anchor, name, value):
        stage = (
            "ledger"
            if name.endswith(".ledger.json")
            else ("pending" if value["status"] == "pending" else "final")
        )
        if phase == "before_" + stage:
            raise OSError("synthetic pre-publication fault")
        actual_write(anchor, name, value)
        if phase == "after_" + stage:
            raise OSError("synthetic post-publication fault")

    with monkeypatch.context() as patch:
        patch.setattr(SyntheticSyncStore, "_write", staticmethod(interrupted))
        with pytest.raises(OSError):
            store.deliver(payload())
    reopened = SyntheticSyncStore(store.root)
    receipt = reopened.get(payload())
    if receipt is None:
        assert phase == "before_pending"
        confirmed = reopened.deliver(payload())
    elif receipt["status"] == "synced":
        assert phase == "after_final"
        confirmed = reopened.deliver(payload())
    else:
        assert receipt["status"] == "pending"
        with pytest.raises(SyntheticSyncError, match="Reconcile"):
            reopened.deliver(payload())
        reconciled = reopened.reconcile(payload())
        confirmed = (
            reopened.deliver(payload())
            if reconciled["status"] == "failed"
            else reconciled
        )
    assert confirmed["status"] == "synced" and confirmed["live_synced"] is False
    assert len(list(store.root.glob("*.ledger.json"))) == 1
    assert reopened.deliver(payload())["synthetic_id"] == confirmed["synthetic_id"]


@pytest.mark.parametrize("directory_fsync", [1, 2, 3])
def test_directory_fsync_failure_reloads_actual_publication(
    tmp_path, monkeypatch, directory_fsync
):
    store = store_or_refusal(tmp_path)
    if store is None:
        return
    import os
    import stat

    from edn.operations import intake_sync

    actual_fsync = os.fsync
    observed = 0

    def failed_directory_sync(descriptor):
        nonlocal observed
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            observed += 1
            if observed == directory_fsync:
                raise OSError("synthetic uncertain directory durability")
        return actual_fsync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(intake_sync.os, "fsync", failed_directory_sync)
        with pytest.raises(OSError):
            store.deliver(payload())
    reopened = SyntheticSyncStore(store.root)
    current = reopened.get(payload())
    assert current is not None
    if current["status"] == "pending":
        with pytest.raises(SyntheticSyncError, match="Reconcile"):
            reopened.deliver(payload())
        current = reopened.reconcile(payload())
    if current["status"] == "failed":
        current = reopened.deliver(payload())
    assert current["status"] == "synced" and current["live_synced"] is False
    assert len(list(store.root.glob("*.ledger.json"))) == 1
