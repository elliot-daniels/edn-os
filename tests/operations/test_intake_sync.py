"""Synthetic transport has durable receipts and never claims live delivery."""

import sys
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeStore
from edn.operations.intake_sync import (
    SyntheticSyncError,
    SyntheticSyncStore,
    delivery_identity,
)
from tests.operations.test_intake import fields


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
        return None, None, None
    root.mkdir(mode=0o700)
    private = tmp_path / "intake"
    private.mkdir(mode=0o700)
    intake = IntakeStore(private / "requests.db")
    intake.initialise()
    request = intake.create(fields(), submission_id=str(uuid4()))
    intake.approve(request.request_id, request.revision)
    snapshot = {
        **intake.export(request.request_id, request.revision),
        "not_synced": True,
    }
    return SyntheticSyncStore(root, intake_store=intake), intake, snapshot


def test_unknown_requires_reconciliation_and_survives_restart(tmp_path):
    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    result = store.deliver(snapshot, "unknown")
    assert result["status"] == "unknown" and result["live_synced"] is False
    assert result["synthetic_id"] is None
    reopened = SyntheticSyncStore(store.root, intake_store=intake)
    with pytest.raises(SyntheticSyncError, match="Reconcile"):
        reopened.deliver(snapshot)
    resolved = reopened.reconcile(snapshot)
    assert resolved["status"] == "synced" and resolved["live_synced"] is False
    assert resolved["synthetic_id"].startswith("SYNTHETIC-")
    assert reopened.deliver(snapshot) == resolved


def test_failed_attempt_can_retry_but_changed_payload_cannot(tmp_path):
    store, _intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    failed = store.deliver(snapshot, "failed")
    assert failed["status"] == "failed" and failed["synthetic_id"] is None
    succeeded = store.deliver(snapshot, "success")
    assert succeeded["status"] == "synced" and succeeded["attempt"] == 2
    changed = dict(snapshot)
    changed["fields"] = {"Title": "changed"}
    with pytest.raises(SyntheticSyncError, match="does not match"):
        store.deliver(changed)
    assert store.get(snapshot) == succeeded


def test_tampered_success_receipt_requires_ledger_confirmation(tmp_path):
    store, _intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    import json

    original = store.deliver(snapshot)
    path = next(store.root.glob("*.receipt.json"))
    tampered = dict(original)
    tampered["synthetic_id"] = "SYNTHETIC-d411af59-c600-413b-a916-a462c395f108"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    for action in (store.get, store.deliver):
        with pytest.raises(SyntheticSyncError, match="inconsistent"):
            action(snapshot)
    assert store.reconcile(snapshot)["synthetic_id"] == original["synthetic_id"]


def test_missing_success_ledger_never_claims_confirmation_or_allows_retry(tmp_path):
    store, _intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    store.deliver(snapshot)
    receipt = next(store.root.glob("*.receipt.json"))
    before = receipt.read_bytes()
    next(store.root.glob("*.ledger.json")).unlink()
    for action in (store.get, store.deliver, store.reconcile):
        with pytest.raises(SyntheticSyncError):
            action(snapshot)
    assert receipt.read_bytes() == before


@pytest.mark.parametrize(
    "phase",
    [
        "before_pending",
        "after_pending",
        "before_work",
        "after_work",
        "before_ledger",
        "after_ledger",
        "before_final",
        "after_final",
    ],
)
def test_interrupted_publication_restarts_without_duplicate_delivery(
    tmp_path, monkeypatch, phase
):
    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    actual_write = SyntheticSyncStore._write

    def interrupted(anchor, name, value):
        stage = (
            "work"
            if name.endswith(".work.json")
            else (
                "ledger"
                if name.endswith(".ledger.json")
                else ("pending" if value["status"] == "pending" else "final")
            )
        )
        if phase == "before_" + stage:
            raise OSError("synthetic pre-publication fault")
        actual_write(anchor, name, value)
        if phase == "after_" + stage:
            raise OSError("synthetic post-publication fault")

    with monkeypatch.context() as patch:
        patch.setattr(SyntheticSyncStore, "_write", staticmethod(interrupted))
        with pytest.raises(OSError):
            store.deliver(snapshot)
    reopened = SyntheticSyncStore(store.root, intake_store=intake)
    receipt = reopened.get(snapshot)
    if receipt is None:
        assert phase == "before_pending"
        confirmed = reopened.deliver(snapshot)
    elif receipt["status"] == "synced":
        assert phase == "after_final"
        confirmed = reopened.deliver(snapshot)
    else:
        assert receipt["status"] == "pending"
        with pytest.raises(SyntheticSyncError, match="Reconcile"):
            reopened.deliver(snapshot)
        reconciled = reopened.reconcile(snapshot)
        confirmed = (
            reopened.deliver(snapshot)
            if reconciled["status"] == "failed"
            else reconciled
        )
    assert confirmed["status"] == "synced" and confirmed["live_synced"] is False
    assert len(list(store.root.glob("*.ledger.json"))) == 1
    assert reopened.deliver(snapshot)["synthetic_id"] == confirmed["synthetic_id"]


@pytest.mark.parametrize("directory_fsync", [1, 2, 3, 4])
def test_directory_fsync_failure_reloads_actual_publication(
    tmp_path, monkeypatch, directory_fsync
):
    store, intake, snapshot = store_or_refusal(tmp_path)
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
            store.deliver(snapshot)
    reopened = SyntheticSyncStore(store.root, intake_store=intake)
    current = reopened.get(snapshot)
    assert current is not None
    if current["status"] == "pending":
        with pytest.raises(SyntheticSyncError, match="Reconcile"):
            reopened.deliver(snapshot)
        current = reopened.reconcile(snapshot)
    if current["status"] == "failed":
        current = reopened.deliver(snapshot)
    assert current["status"] == "synced" and current["live_synced"] is False
    assert len(list(store.root.glob("*.ledger.json"))) == 1


def next_version(intake, snapshot):
    request = intake.get(snapshot["request_id"])
    revised = intake.update(
        request.request_id,
        request.revision,
        {**request.fields, "jobDescription": "Corrected synthetic work"},
    )
    intake.approve(revised.request_id, revised.revision)
    return {**intake.export(revised.request_id, revised.revision), "not_synced": True}


@pytest.mark.parametrize("prior_outcome", ["failed", "success"])
def test_corrected_approved_version_uses_one_receiver_work_identity(
    tmp_path, prior_outcome
):
    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    prior = store.deliver(snapshot, prior_outcome)
    current = next_version(intake, snapshot)
    assert current["idempotency_key"] == snapshot["idempotency_key"]
    assert (
        delivery_identity(current)["idempotency_key"]
        != delivery_identity(snapshot)["idempotency_key"]
    )
    assert store.get(current) is None
    revised = store.deliver(current)
    assert revised["status"] == "synced" and revised["live_synced"] is False
    if prior_outcome == "success":
        assert revised["synthetic_id"] == prior["synthetic_id"]
    assert len(list(store.root.glob("*.work.json"))) == 1
    assert store.deliver(current) == revised


def test_older_unknown_version_can_reconcile_without_original_source_body(tmp_path):
    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    old = store.deliver(snapshot, "unknown")
    current = next_version(intake, snapshot)
    unresolved = store.unconfirmed(current)
    assert unresolved == (old,)
    with pytest.raises(SyntheticSyncError, match="Reconcile"):
        store.deliver(current)
    previous = store.reconcile_record(current, unresolved[0]["identity"])
    assert previous["status"] == "synced"
    assert store.unconfirmed(current) == ()
    assert store.deliver(current)["synthetic_id"] == previous["synthetic_id"]


@pytest.mark.parametrize("mutation", ["edited", "cancelled", "unknown"])
def test_delivery_rechecks_current_store_and_writes_no_receipt(tmp_path, mutation):
    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    before = intake.path.read_bytes()
    if mutation == "edited":
        current = intake.get(snapshot["request_id"])
        intake.update(
            current.request_id,
            current.revision,
            {**current.fields, "jobDescription": "Changed after approval"},
        )
    elif mutation == "cancelled":
        intake.transition(
            snapshot["request_id"],
            snapshot["revision"],
            "cancelled",
            reason="Synthetic cancellation",
        )
    else:
        snapshot = {**snapshot, "request_id": str(uuid4())}
    authoritative = intake.path.read_bytes()
    with pytest.raises(SyntheticSyncError, match="current intake approval"):
        store.deliver(snapshot)
    assert intake.path.read_bytes() == authoritative
    assert not list(store.root.glob("*.receipt.json"))
    assert not list(store.root.glob("*.ledger.json"))
    assert not list(store.root.glob("*.work.json"))
    if mutation == "unknown":
        assert authoritative == before


def test_missing_intake_authority_cannot_publish_delivery(tmp_path):
    store, _, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    unauthorised = SyntheticSyncStore(store.root)
    with pytest.raises(SyntheticSyncError, match="authority is required"):
        unauthorised.deliver(snapshot)
    assert not list(store.root.glob("*.json"))


def test_reference_existing_delivery_is_refused_without_new_item(tmp_path):
    store, _, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    snapshot = {**snapshot, "operation": "reference_existing"}
    with pytest.raises(SyntheticSyncError, match="reference-only"):
        store.deliver(snapshot)
    assert not list(store.root.glob("*.json"))


def test_changed_evidence_at_send_time_has_typed_refusal_and_no_receipt(tmp_path):
    import hashlib
    import json

    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    evidence = tmp_path / "evidence"
    evidence.mkdir(mode=0o700)
    request = intake.get(snapshot["request_id"])
    folder = evidence / request.request_id
    folder.mkdir(mode=0o700)
    identifier = str(uuid4())
    item = folder / identifier
    item.mkdir(mode=0o700)
    raw = b"Synthetic proof\n"
    metadata = {
        "attachment_id": identifier,
        "request_id": request.request_id,
        "original_name": "proof.txt",
        "media_type": "text/plain",
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    receipt = {
        "schema_version": 1,
        "request_id": request.request_id,
        "entries": [
            {"attachment_id": identifier, "size_bytes": len(raw), "state": "complete"}
        ],
    }
    for path, data in (
        (item / "original.bin", raw),
        (item / "metadata.json", json.dumps(metadata).encode()),
        (folder / "attachments.json", json.dumps(receipt).encode()),
    ):
        path.write_bytes(data)
        path.chmod(0o600)
    intake = IntakeStore(intake.path, evidence_root=evidence)
    revised = intake.update(
        request.request_id, request.revision, request.fields, attachments=(metadata,)
    )
    intake.approve(revised.request_id, revised.revision)
    snapshot = {
        **intake.export(revised.request_id, revised.revision),
        "not_synced": True,
    }
    store = SyntheticSyncStore(store.root, intake_store=intake)
    (item / "original.bin").write_bytes(b"Mutated after export")
    before = intake.path.read_bytes()
    with pytest.raises(SyntheticSyncError, match="current intake approval"):
        store.deliver(snapshot)
    assert intake.path.read_bytes() == before
    assert not list(store.root.glob("*.json"))


def test_delivery_holds_intake_lock_until_transport_publication(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    store, intake, snapshot = store_or_refusal(tmp_path)
    if store is None:
        return
    attempting, finished = Event(), Event()
    write = SyntheticSyncStore._write

    def edit():
        attempting.set()
        intake.update(
            snapshot["request_id"],
            snapshot["revision"],
            fields(jobDescription="Concurrent correction"),
        )
        finished.set()

    with ThreadPoolExecutor(max_workers=1) as worker:
        task = None

        def checked_write(anchor, name, value):
            nonlocal task
            if task is None:
                task = worker.submit(edit)
                assert attempting.wait(3)
            assert not finished.is_set()
            write(anchor, name, value)

        with monkeypatch.context() as patch:
            patch.setattr(SyntheticSyncStore, "_write", staticmethod(checked_write))
            result = store.deliver(snapshot)
        assert result["status"] == "synced"
        task.result(timeout=3)
    assert finished.is_set()
    assert intake.get(snapshot["request_id"]).state == "draft"
