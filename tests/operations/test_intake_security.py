"""Native fail-closed protection and explicit self-approval audit evidence."""

import os
import stat
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeStore
from edn.operations.intake_security import (
    IntakeSecurityError,
    protect_file,
    request_lock,
    validate_root,
)
from tests.operations.test_intake import fields, store


def test_native_unsupported_storage_all_entrypoints_do_not_touch_files(tmp_path):
    if os.name == "posix":
        tmp_path.chmod(0o700)
        assert validate_root(tmp_path) == tmp_path
        return
    path = tmp_path / "requests.db"
    requests = IntakeStore(path)
    for action in (
        requests.initialise,
        requests.list_requests,
        lambda: requests.create(fields(), submission_id=str(uuid4())),
    ):
        with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
            action()
    assert not path.exists() and tuple(tmp_path.iterdir()) == ()


def test_owned_modes_links_and_self_approval_audit(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    assert stat.S_IMODE(requests.path.stat().st_mode) == 0o600
    request = requests.create(fields(), submission_id=str(uuid4()))
    approved = requests.approve(request.request_id, 1)
    assert "self-approval" in approved.approval_actor
    assert approved.approval_timestamp
    audit = requests.audit_history(request.request_id)
    assert audit[0]["revision"] == 1 and audit[0]["decision"] == "created"
    assert audit[1]["decision"] == "approved"
    requests.update(request.request_id, 1, fields(reference="changed"))
    history = requests.audit_history(request.request_id)
    assert history[:2] == audit
    assert [entry["decision"] for entry in history] == [
        "created",
        "approved",
        "edited_approval_invalidated",
    ]
    assert [entry["revision"] for entry in history] == [1, 1, 2]
    assert history[2]["content_hash"] != history[1]["content_hash"]
    assert requests.get(request.request_id).approval_actor is None
    link = tmp_path / "hardlink.db"
    os.link(requests.path, link)
    with pytest.raises(IntakeSecurityError):
        requests.list_requests()
    link.unlink()
    requests.path.chmod(0o644)
    with pytest.raises(IntakeSecurityError):
        requests.list_requests()
    requests.path.chmod(0o600)
    alias = tmp_path / "alias.db"
    alias.symlink_to(requests.path)
    with pytest.raises(OSError):
        protect_file(alias)
    with request_lock(tmp_path, request.request_id):
        assert (
            stat.S_IMODE((tmp_path / (request.request_id + ".lock")).stat().st_mode)
            == 0o600
        )


def test_unsafe_root_fails_before_create(tmp_path):
    if os.name != "posix":
        assert store(tmp_path) is None
        return
    tmp_path.chmod(0o755)
    with pytest.raises(IntakeSecurityError):
        IntakeStore(tmp_path / "requests.db").initialise()
    assert not (tmp_path / "requests.db").exists()


def test_contract_validation_runs_on_every_platform():
    from edn.operations.intake import validate_fields

    assert validate_fields(fields())["email"] == "a@example.com"
    with pytest.raises(ValueError):
        validate_fields(fields(jobDescription="\ud800"))


def test_missing_store_read_has_fixed_database_error_without_private_path(tmp_path):
    import sqlite3
    import traceback

    if os.name != "posix":
        assert store(tmp_path) is None
        return
    tmp_path.chmod(0o700)
    path = tmp_path / "synthetic-private-request-store.db"
    with pytest.raises(sqlite3.OperationalError) as raised:
        IntakeStore(path, read_only=True).list_requests()
    assert str(raised.value) == "Request store is unavailable"
    assert str(path) not in "".join(traceback.format_exception(raised.value))
    assert not path.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor", ""),
        ("actor", "invented authenticated actor"),
        ("decided_at", "not-a-timestamp"),
        ("decided_at", "2026-10-08T12:00:00"),
        ("decided_at", "2026-10-08T12:00:00+10:00"),
        ("decision_id", "bad-id"),
        ("content_hash", "b" * 64),
        ("revision", 99),
    ],
)
def test_corrupt_audit_refuses_get_export_history_without_write(tmp_path, field, value):
    import sqlite3

    requests = store(tmp_path)
    if requests is None:
        return
    request = requests.create(fields(), submission_id=str(uuid4()))
    requests.approve(request.request_id, 1)
    with sqlite3.connect(requests.path) as connection:
        connection.execute(
            f"UPDATE intake_approvals SET {field}=? WHERE decision='approved'", (value,)
        )
    before = requests.path.read_bytes()
    for action in (
        lambda: requests.get(request.request_id),
        lambda: requests.export(request.request_id, 1),
        lambda: requests.audit_history(request.request_id),
    ):
        with pytest.raises(ValueError):
            action()
    assert requests.path.read_bytes() == before


@pytest.mark.parametrize("hidden", ["\t", "\n", "\r", "\ufeff", "\u200b", "\u202e"])
def test_hidden_single_line_contract_controls_rejected_every_platform(hidden):
    from edn.operations.intake import validate_fields

    with pytest.raises(ValueError):
        validate_fields(fields(contactName="Alex" + hidden + "Smith"))


def test_parent_swap_cannot_redirect_anchored_sqlite_writes(tmp_path, monkeypatch):
    import sqlite3

    from edn.operations import intake

    requests = store(tmp_path)
    if requests is None:
        return
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir(mode=0o700)
    sentinel = outside / "requests.db"
    sentinel.write_bytes(b"outside-sentinel")
    sentinel.chmod(0o600)
    moved = tmp_path.parent / (tmp_path.name + "-moved")
    actual_connect = sqlite3.connect
    swapped = False

    def swap_before_connect(*args, **kwargs):
        nonlocal swapped
        if not swapped:
            tmp_path.rename(moved)
            tmp_path.symlink_to(outside, target_is_directory=True)
            swapped = True
        return actual_connect(*args, **kwargs)

    monkeypatch.setattr(intake.sqlite3, "connect", swap_before_connect)
    from contextlib import suppress

    with suppress(ValueError, sqlite3.Error, OSError):
        requests.create(fields(), submission_id=str(uuid4()))
    assert sentinel.read_bytes() == b"outside-sentinel"
    assert tuple(outside.iterdir()) == (sentinel,)


def test_backend_manifest_gate_and_queue_corruption_isolation(tmp_path):
    import sqlite3
    from uuid import uuid4

    requests = store(tmp_path)
    if requests is None:
        return
    first = requests.create(fields(), submission_id=str(uuid4()))
    second = requests.create(fields(), submission_id=str(uuid4()))
    metadata = {
        "attachment_id": str(uuid4()),
        "request_id": first.request_id,
        "original_name": "proof.pdf",
        "media_type": "application/pdf",
        "size_bytes": 10,
        "sha256": "a" * 64,
    }
    changed = requests.update(first.request_id, 1, first.fields, attachments=[metadata])
    with pytest.raises(ValueError, match="evidence"):
        requests.approve(first.request_id, changed.revision)
    with sqlite3.connect(requests.path) as connection:
        connection.execute(
            "UPDATE intake_revisions SET fields='bad-json' WHERE request_id=?",
            (first.request_id,),
        )
    result = requests.list_requests_with_diagnostics()
    assert result.requests == (second,) and result.malformed == 1
    with pytest.raises(ValueError):
        requests.get(first.request_id)


@pytest.mark.parametrize("mutation", ["missing", "bytes", "metadata", "reserved"])
def test_backend_actual_evidence_corruption_blocks_approval_and_export(
    tmp_path, mutation
):
    import hashlib
    import json
    from uuid import uuid4

    from edn.operations.intake_security import verify_evidence

    requests = store(tmp_path)
    if requests is None:
        return
    evidence = tmp_path / "evidence"
    evidence.mkdir(mode=0o700)
    request = requests.create(fields(), submission_id=str(uuid4()))
    request_root = evidence / request.request_id
    request_root.mkdir(mode=0o700)
    attachment_id = str(uuid4())
    attachment = request_root / attachment_id
    attachment.mkdir(mode=0o700)
    payload = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
    metadata = {
        "attachment_id": attachment_id,
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
                "attachment_id": attachment_id,
                "size_bytes": len(payload),
                "state": "complete",
            }
        ],
    }
    for path, content in (
        (attachment / "original.bin", payload),
        (attachment / "metadata.json", json.dumps(metadata).encode()),
        (request_root / "attachments.json", json.dumps(receipt).encode()),
    ):
        path.write_bytes(content)
        path.chmod(0o600)
    verify_evidence(evidence, request.request_id, (metadata,))
    requests = IntakeStore(requests.path, evidence_root=evidence)
    changed = requests.update(
        request.request_id, 1, request.fields, attachments=[metadata]
    )
    requests.approve(request.request_id, changed.revision)
    if mutation == "missing":
        (attachment / "original.bin").unlink()
    elif mutation == "bytes":
        (attachment / "original.bin").write_bytes(b"tampered")
    elif mutation == "metadata":
        (attachment / "metadata.json").write_text("{}")
    else:
        receipt["entries"][0]["state"] = "reserved"
        (request_root / "attachments.json").write_text(json.dumps(receipt))
    before = requests.path.read_bytes()
    for action in (requests.approve, requests.export):
        with pytest.raises(ValueError, match="evidence"):
            action(request.request_id, changed.revision)
    assert requests.path.read_bytes() == before


def test_final_database_symlink_swap_rejected_before_sql_and_outside_unchanged(
    tmp_path, monkeypatch
):
    import sqlite3

    from edn.operations import intake

    requests = store(tmp_path)
    if requests is None:
        return
    outside = tmp_path / "outside.db"
    with sqlite3.connect(outside) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('unchanged')")
    outside.chmod(0o600)
    before = outside.read_bytes()
    actual_connect = sqlite3.connect
    swapped = False

    def swap_before_connect(*args, **kwargs):
        nonlocal swapped
        if not swapped:
            requests.path.rename(tmp_path / "original.db")
            requests.path.symlink_to(outside)
            swapped = True
        return actual_connect(*args, **kwargs)

    monkeypatch.setattr(intake.sqlite3, "connect", swap_before_connect)
    with pytest.raises((ValueError, OSError)):
        requests.create(fields(), submission_id=str(uuid4()))
    assert outside.read_bytes() == before


def test_snapshot_roundtrip_readonly_and_failed_publication_preserve_original(
    tmp_path, monkeypatch
):
    import sqlite3

    from edn.operations.intake_security import AnchoredDirectory

    requests = store(tmp_path)
    if requests is None:
        return
    request = requests.create(fields(), submission_id=str(uuid4()))
    original = requests.path.read_bytes()
    assert original.startswith(b"SQLite format 3\x00")
    assert IntakeStore(requests.path, read_only=True).get(request.request_id) == request
    assert requests.path.read_bytes() == original
    with sqlite3.connect(requests.path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    def failed_replace(*args, **kwargs):
        raise OSError("synthetic disk publication failure")

    monkeypatch.setattr(AnchoredDirectory, "replace", failed_replace)
    with pytest.raises(OSError):
        requests.update(request.request_id, 1, fields(reference="uncommitted"))
    assert requests.path.read_bytes() == original
    assert IntakeStore(requests.path).get(request.request_id) == request
    assert not any(".pending-" in path.name for path in tmp_path.iterdir())
