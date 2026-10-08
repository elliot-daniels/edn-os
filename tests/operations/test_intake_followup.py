"""QA-driven physical accounting, lifecycle and uncertainty boundaries."""

import os
import stat

import pytest

from edn.operations.intake import (
    IntakeCommitUncertainError,
    IntakeError,
    IntakeStore,
    validate_fields,
)
from edn.operations.intake_security import AnchoredDirectory, IntakeSecurityError
from tests.operations.test_intake import fields, store


@pytest.mark.parametrize("value", ["Syn\u2028x", "Syn\u2029x"])
def test_unicode_separator_rejected_on_every_platform(value):
    with pytest.raises(IntakeError):
        validate_fields(fields(contactName=value))


@pytest.mark.parametrize("source", ["draft", "approved", "rejected", "cancelled"])
@pytest.mark.parametrize("target", ["draft", "approved", "rejected", "cancelled"])
def test_exhaustive_state_transition_table(tmp_path, source, target):
    requests = store(tmp_path)
    if requests is None:
        return
    request = requests.create(fields())
    if source == "approved":
        request = requests.approve(request.request_id, 1)
    elif source in {"rejected", "cancelled"}:
        request = requests.transition(
            request.request_id, 1, source, reason="Synthetic decision"
        )
    allowed = {
        ("draft", "approved"),
        ("draft", "rejected"),
        ("draft", "cancelled"),
        ("approved", "rejected"),
        ("approved", "cancelled"),
        ("rejected", "draft"),
    }
    action = (
        (lambda: requests.approve(request.request_id, request.revision))
        if target == "approved"
        else (
            lambda: requests.transition(
                request.request_id, request.revision, target, reason="Synthetic reason"
            )
        )
    )
    if (source, target) in allowed:
        result = action()
        assert result.state == target
        history = requests.audit_history(request.request_id)
        assert history[-1]["decision"] == (
            "approved"
            if target == "approved"
            else "reopened"
            if target == "draft"
            else target
        )
        if target != "approved":
            assert history[-1]["reason"] == "Synthetic reason"
    else:
        before = requests.path.read_bytes()
        with pytest.raises(IntakeError):
            action()
        assert requests.path.read_bytes() == before


def test_bad_lock_repeatedly_releases_anchor_fd_and_fifo_fails_immediately(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    lock = tmp_path / "requests.db.lock"
    lock.chmod(0o644)
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(30):
        with pytest.raises((ValueError, OSError)):
            requests.list_requests()
    assert len(os.listdir("/proc/self/fd")) == before
    lock.chmod(0o600)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    with AnchoredDirectory(tmp_path) as directory, pytest.raises(IntakeSecurityError):
        directory.open_file("fifo")


def test_post_publish_sync_failure_is_uncertain_and_reload_finds_actual_revision(
    tmp_path, monkeypatch
):
    requests = store(tmp_path)
    if requests is None:
        return
    request = requests.create(fields())
    original_sync = os.fsync

    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("synthetic directory-sync failure")
        return original_sync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(IntakeCommitUncertainError, match="unconfirmed"):
        requests.update(request.request_id, 1, fields(reference="published"))
    reopened = IntakeStore(requests.path).get(request.request_id)
    assert reopened.revision == 2 and reopened.fields["reference"] == "published"


@pytest.mark.parametrize(
    "mutation", ["orphan", "reserved", "unselected_size", "bool_version"]
)
def test_backend_physical_orphans_and_receipt_corruption_refuse_approval(
    tmp_path, mutation
):
    import hashlib
    import json
    from uuid import uuid4

    requests = store(tmp_path)
    if requests is None:
        return
    root = tmp_path / "evidence"
    root.mkdir(mode=0o700)
    request = requests.create(fields())
    directory = root / request.request_id
    directory.mkdir(mode=0o700)
    identifier = str(uuid4())
    attached = directory / identifier
    attached.mkdir(mode=0o700)
    payload = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
    metadata = {
        "attachment_id": identifier,
        "request_id": request.request_id,
        "original_name": "proof.pdf",
        "media_type": "application/pdf",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    receipt = {
        "schema_version": 1,
        "request_id": request.request_id,
        "entries": [
            {
                "attachment_id": identifier,
                "size_bytes": len(payload),
                "state": "complete",
            }
        ],
    }

    def private(path, value):
        path.write_bytes(value)
        path.chmod(0o600)

    private(attached / "original.bin", payload)
    private(attached / "metadata.json", json.dumps(metadata).encode())
    if mutation == "orphan":
        private(directory / "unexpected.bin", b"orphan")
    elif mutation == "bool_version":
        receipt["schema_version"] = True
    else:
        extra = str(uuid4())
        folder = directory / extra
        folder.mkdir(mode=0o700)
        private(folder / "original.bin", b"too-large")
        receipt["entries"].append(
            {
                "attachment_id": extra,
                "size_bytes": 1,
                "state": "reserved" if mutation == "reserved" else "complete",
            }
        )
    private(directory / "attachments.json", json.dumps(receipt).encode())
    requests = IntakeStore(requests.path, evidence_root=root)
    revised = requests.update(
        request.request_id, 1, request.fields, attachments=[metadata]
    )
    before = requests.path.read_bytes()
    with pytest.raises(ValueError, match="evidence"):
        requests.approve(request.request_id, revised.revision)
    assert requests.path.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    ["forged_rejected", "forged_cancelled", "missing_edit", "missing_reopen"],
)
def test_current_state_requires_matching_current_revision_audit(tmp_path, mutation):
    import sqlite3

    requests = store(tmp_path)
    if requests is None:
        return
    request = requests.create(fields())
    if mutation == "missing_edit":
        requests.update(request.request_id, 1, fields(reference="edited"))
    elif mutation == "missing_reopen":
        rejected = requests.transition(
            request.request_id, 1, "rejected", reason="Synthetic reject"
        )
        requests.transition(
            request.request_id, rejected.revision, "draft", reason="Synthetic reopen"
        )
    with sqlite3.connect(requests.path) as connection:
        if mutation.startswith("forged"):
            connection.execute(
                "UPDATE intake_requests SET state=?",
                (mutation.removeprefix("forged_"),),
            )
        else:
            connection.execute(
                "DELETE FROM intake_approvals WHERE rowid="
                "(SELECT max(rowid) FROM intake_approvals)"
            )
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError):
        requests.get(request.request_id)
    result = requests.list_requests_with_diagnostics()
    assert result.requests == () and result.malformed == 1
    with pytest.raises(IntakeError):
        requests.export(request.request_id, 1)
    assert requests.path.read_bytes() == before
