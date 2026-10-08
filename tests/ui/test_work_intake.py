"""Synthetic create, review, approval, restart and honest export lifecycle."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from edn.operations.intake import IntakeStore
from edn.ui.work_intake_app import attach_file

SCRIPT = "from edn.ui.work_intake_app import render\nrender()"
FIELDS = {
    "contactName": "Synthetic Alex",
    "company": "Example Company",
    "email": "alex@example.invalid",
    "phone": "+61400000000",
    "siteLocation": "Synthetic site",
    "serviceRequired": "Field engineering",
    "preferredDate": "",
    "urgency": "Routine",
    "jobDescription": "Inspect the synthetic network.",
    "reference": "TEST-ONLY",
}


def button(app: AppTest, label: str):
    return next(item for item in app.button if item.label == label)


def initialise(tmp_path: Path, monkeypatch):
    root = tmp_path / "demo"
    root.mkdir(mode=0o700)
    (root / "attachments").mkdir(mode=0o700)
    (root / "synthetic-sync").mkdir(mode=0o700)
    store = IntakeStore(root / "requests.db", evidence_root=root / "attachments")
    store.initialise()
    store.begin_submission()
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(root))
    return root, store


def unsupported_app(tmp_path, monkeypatch):
    if sys.platform == "linux":
        return False
    before = tuple(tmp_path.iterdir())
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path / "must-not-exist"))
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert "requires Linux or WSL" in "\n".join(item.value for item in app.error)
    assert tuple(tmp_path.iterdir()) == before
    return True


def test_manual_review_approval_export_restart_and_correction(tmp_path, monkeypatch):
    if unsupported_app(tmp_path, monkeypatch):
        return
    _, store = initialise(tmp_path, monkeypatch)
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    intent = store.current_submission()
    assert intent is not None
    create_key = f"create-{intent.submission_id}"
    for field in (
        "contactName",
        "company",
        "email",
        "phone",
        "siteLocation",
        "reference",
    ):
        app.text_input(key=f"{create_key}-{field}").set_value(FIELDS[field])
    app.text_area(key=f"{create_key}-jobDescription").set_value(
        FIELDS["jobDescription"]
    )
    app.selectbox(key=f"{create_key}-serviceRequired").select(FIELDS["serviceRequired"])
    button(app, "Save request locally").click().run()
    assert not app.exception
    request = store.list_requests()[0]
    assert request.fields == FIELDS
    assert request.state == "draft" and request.sync_status == "not_synced"
    assert button(app, "Prepare SharePoint record (dry run)").disabled
    button(app, "Approve reviewed request (self-approval)").click().run()
    assert not app.exception
    assert store.get(request.request_id).state == "approved"
    decision = next(
        item
        for item in store.audit_history(request.request_id)
        if item["decision"] == "approved"
    )
    assert decision["revision"] == request.revision
    assert len(decision["content_hash"]) == 64
    assert "self-approval" in decision["actor"]
    assert str(decision["content_hash"]) in [item.value for item in app.code]
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception
    assert "Nothing has been sent" in "\n".join(item.value for item in app.success)
    assert store.get(request.request_id).sync_status == "dry_run"
    reopened = AppTest.from_string(SCRIPT).run()
    assert not reopened.exception
    assert "not sent to SharePoint" in "\n".join(
        item.value for item in reopened.caption
    )
    current = store.get(request.request_id)
    reopened.text_input(
        key=f"review-{request.request_id}-{current.revision}-siteLocation"
    ).set_value("Corrected synthetic site")
    button(reopened, "Save corrections").click().run()
    assert not reopened.exception
    changed = store.get(request.request_id)
    assert changed.fields["siteLocation"] == "Corrected synthetic site"
    assert changed.state == "draft" and changed.sync_status == "not_synced"
    assert button(reopened, "Prepare SharePoint record (dry run)").disabled


def test_failed_save_does_not_claim_local_or_sharepoint_success(tmp_path, monkeypatch):
    if unsupported_app(tmp_path, monkeypatch):
        return
    _, store = initialise(tmp_path, monkeypatch)
    app = AppTest.from_string(SCRIPT).run()
    button(app, "Save request locally").click().run()
    assert not app.exception
    assert app.error and not app.success
    assert store.list_requests() == ()


def test_attachment_metadata_is_linked_and_requires_reapproval(tmp_path, monkeypatch):
    if unsupported_app(tmp_path, monkeypatch):
        return
    from edn.operations.intake_attachments import IntakeAttachmentStore

    root, store = initialise(tmp_path, monkeypatch)
    request = store.create(FIELDS, submission_id=str(uuid4()))
    store.approve(request.request_id, request.revision)
    request = store.get(request.request_id)
    files = IntakeAttachmentStore(root / "attachments")
    attach_file(store, files, request, "support.pdf", b"%PDF-1.4\nsynthetic\n%%EOF\n")
    updated = store.get(request.request_id)
    assert updated.state == "draft" and updated.sync_status == "not_synced"
    assert len(updated.attachments) == 1
    assert (
        files.read(request.request_id, updated.attachments[0]["attachment_id"])
        == b"%PDF-1.4\nsynthetic\n%%EOF\n"
    )
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert any("support.pdf" in item.value for item in app.text)


def test_missing_configuration_does_not_initialise(tmp_path, monkeypatch):
    if unsupported_app(tmp_path, monkeypatch):
        return
    monkeypatch.delenv("EDN_INTAKE_ROOT", raising=False)
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception and app.info
    assert not list(tmp_path.iterdir())


def test_changed_supporting_file_blocks_approval_and_dry_run(tmp_path, monkeypatch):
    if unsupported_app(tmp_path, monkeypatch):
        return
    from edn.operations.intake_attachments import IntakeAttachmentStore

    root, store = initialise(tmp_path, monkeypatch)
    request = store.create(FIELDS, submission_id=str(uuid4()))
    files = IntakeAttachmentStore(root / "attachments")
    attach_file(store, files, request, "proof.pdf", b"%PDF-1.4\nsynthetic\n%%EOF\n")
    request = store.get(request.request_id)
    original = root / "attachments" / request.request_id
    original = original / str(request.attachments[0]["attachment_id"]) / "original.bin"
    original.write_bytes(b"%PDF-1.4\nchanged\n%%EOF\n")
    before = (root / "requests.db").read_bytes()
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert "integrity is unconfirmed" in "\n".join(item.value for item in app.error)
    assert button(app, "Approve reviewed request (self-approval)").disabled
    assert button(app, "Prepare SharePoint record (dry run)").disabled
    assert (root / "requests.db").read_bytes() == before


def fill_manual(app, store):
    intent = store.current_submission()
    assert intent is not None
    prefix = f"create-{intent.submission_id}"
    for name in (
        "contactName",
        "company",
        "email",
        "phone",
        "siteLocation",
        "reference",
    ):
        app.text_input(key=f"{prefix}-{name}").set_value(FIELDS[name])
    app.text_area(key=f"{prefix}-jobDescription").set_value(FIELDS["jobDescription"])
    app.selectbox(key=f"{prefix}-serviceRequired").select(FIELDS["serviceRequired"])


def test_lost_save_acknowledgement_reopens_same_submission_without_duplicate(
    tmp_path, monkeypatch
):
    if unsupported_app(tmp_path, monkeypatch):
        return
    _, store = initialise(tmp_path, monkeypatch)
    app = AppTest.from_string(SCRIPT).run()
    fill_manual(app, store)
    actual_create = IntakeStore.create

    def lost_acknowledgement(self, *args, **kwargs):
        actual_create(self, *args, **kwargs)
        raise ValueError("synthetic lost acknowledgement")

    with monkeypatch.context() as patch:
        patch.setattr(IntakeStore, "create", lost_acknowledgement)
        button(app, "Save request locally").click().run()
    assert not app.exception and app.error
    assert len(store.list_requests()) == 1
    intent = store.current_submission()
    reopened = AppTest.from_string(SCRIPT).run()
    assert not reopened.exception
    assert store.current_submission() == intent
    button(reopened, "Save request locally").click().run()
    assert not reopened.exception
    assert len(store.list_requests()) == 1
    assert store.list_requests()[0].revision == 1


def test_file_upload_approval_export_and_synthetic_failure_reconciliation(
    tmp_path, monkeypatch
):
    if unsupported_app(tmp_path, monkeypatch):
        return
    import io

    import streamlit as st

    _, store = initialise(tmp_path, monkeypatch)
    original_widget = st.file_uploader

    def synthetic_widget(label, *args, **kwargs):
        actual = original_widget(label, *args, **kwargs)
        if label != "Supporting document or photo":
            return actual
        upload = io.BytesIO(b"Synthetic supporting evidence.\n")
        upload.name = "support.txt"
        return upload

    monkeypatch.setattr(st, "file_uploader", synthetic_widget)
    app = AppTest.from_string(SCRIPT).run()
    fill_manual(app, store)
    button(app, "Save request locally").click().run()
    button(app, "Save supporting file").click().run()
    assert not app.exception
    request = store.list_requests()[0]
    assert len(request.attachments) == 1 and request.revision == 2
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception
    prepared = app.session_state["prepared-record"]
    assert prepared["attachment_manifest"]["total_bytes"] == len(
        b"Synthetic supporting evidence.\n"
    )
    assert prepared["not_synced"] is True
    next(
        item for item in app.selectbox if item.label == "Simulated transport outcome"
    ).select("failed")
    button(app, "Run synthetic sync").click().run()
    assert not app.exception
    assert any("Synthetic transport: failed" in item.value for item in app.markdown)
    next(
        item for item in app.selectbox if item.label == "Simulated transport outcome"
    ).select("unknown")
    button(app, "Run synthetic sync").click().run()
    assert not app.exception and button(app, "Run synthetic sync").disabled
    button(app, "Reconcile synthetic attempt").click().run()
    assert not app.exception
    assert any("Synthetic transport: synced" in item.value for item in app.markdown)
    assert any("live SharePoint: not synced" in item.value for item in app.markdown)
    import json
    from uuid import uuid4

    from edn.operations.intake_sync import SyntheticSyncStore

    receipt_path = next((store.path.parent / "synthetic-sync").glob("*.receipt.json"))
    recorded = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected_id = recorded["synthetic_id"]
    recorded["synthetic_id"] = "SYNTHETIC-" + str(uuid4())
    receipt_path.write_text(json.dumps(recorded), encoding="utf-8")
    app.run()
    assert not app.exception
    assert any("status is unconfirmed" in item.value for item in app.error)
    assert button(app, "Run synthetic sync").disabled
    assert not button(app, "Reconcile synthetic attempt").disabled
    assert not any("not attempted" in item.value for item in app.info)
    button(app, "Reconcile synthetic attempt").click().run()
    assert not app.exception
    restored = SyntheticSyncStore(store.path.parent / "synthetic-sync").get(prepared)
    assert restored["synthetic_id"] == expected_id and restored["live_synced"] is False
    current = store.get(request.request_id)
    app.text_input(
        key=f"review-{request.request_id}-{current.revision}-reference"
    ).set_value("REVIEWED-VERSION-3")
    button(app, "Save corrections").click().run()
    assert not app.exception
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception and not button(app, "Run synthetic sync").disabled
    next(
        item for item in app.selectbox if item.label == "Simulated transport outcome"
    ).select("unknown")
    button(app, "Run synthetic sync").click().run()
    assert not app.exception
    current = store.get(request.request_id)
    app.text_input(
        key=f"review-{request.request_id}-{current.revision}-reference"
    ).set_value("REVIEWED-VERSION-4")
    button(app, "Save corrections").click().run()
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception and button(app, "Run synthetic sync").disabled
    assert not button(app, "Reconcile prior version").disabled
    button(app, "Reconcile prior version").click().run()
    assert not app.exception and not button(app, "Run synthetic sync").disabled
    next(
        item for item in app.selectbox if item.label == "Simulated transport outcome"
    ).select("success")
    button(app, "Run synthetic sync").click().run()
    assert not app.exception
    newest = app.session_state["prepared-record"]
    confirmed = SyntheticSyncStore(store.path.parent / "synthetic-sync").get(newest)
    assert (
        confirmed["synthetic_id"] == expected_id and confirmed["live_synced"] is False
    )


def test_synthetic_import_and_manual_share_queue_without_duplicate_create_proposal(
    tmp_path, monkeypatch
):
    if unsupported_app(tmp_path, monkeypatch):
        return
    import io

    import streamlit as st

    _, store = initialise(tmp_path, monkeypatch)
    fixture = (
        Path(__file__).resolve().parents[2]
        / "examples/work-intake/synthetic-request.json"
    )
    original_widget = st.file_uploader

    def source_widget(label, *args, **kwargs):
        actual = original_widget(label, *args, **kwargs)
        if label != "Synthetic request contract":
            return actual
        uploaded = io.BytesIO(fixture.read_bytes())
        uploaded.name = "synthetic-request.json"
        return uploaded

    monkeypatch.setattr(st, "file_uploader", source_widget)
    app = AppTest.from_string(SCRIPT).run()
    fill_manual(app, store)
    button(app, "Save request locally").click().run()
    next(
        item for item in app.text_input if item.label == "Synthetic source request ID"
    ).set_value("SYNTHETIC-AUTO-001")
    button(app, "Import synthetic request").click().run()
    assert not app.exception
    queued = store.list_requests()
    assert len(queued) == 2
    imported = next(item for item in queued if item.source_type == "synthetic_import")
    next(item for item in app.selectbox if item.label == "Select a request").select(
        imported.request_id
    )
    app.run()
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception
    prepared = app.session_state["prepared-record"]
    assert prepared["operation"] == "reference_existing"
    assert prepared["target"]["native_item_id"] == "SYNTHETIC-AUTO-001"
    assert prepared["source_provenance"]["synthetic_only"] is True
    assert all(
        item.label != "Download SharePoint create payload"
        for item in app.get("download_button")
    )


@pytest.mark.parametrize("prior_outcome", ["failed", "success"])
def test_reviewed_correction_after_known_sync_outcome_remains_deliverable(
    tmp_path, monkeypatch, prior_outcome
):
    if unsupported_app(tmp_path, monkeypatch):
        return
    from edn.operations.intake_sync import SyntheticSyncStore

    root, store = initialise(tmp_path, monkeypatch)
    request = store.create(FIELDS, submission_id=str(uuid4()))
    app = AppTest.from_string(SCRIPT).run()
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    original = app.session_state["prepared-record"]
    next(
        item for item in app.selectbox if item.label == "Simulated transport outcome"
    ).select(prior_outcome)
    button(app, "Run synthetic sync").click().run()
    assert not app.exception
    receipt = SyntheticSyncStore(root / "synthetic-sync").get(original)
    app.text_input(key=f"review-{request.request_id}-1-reference").set_value(
        "CORRECTED-AFTER-SYNC"
    )
    button(app, "Save corrections").click().run()
    assert (
        not app.exception
        and button(app, "Prepare SharePoint record (dry run)").disabled
    )
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception and not button(app, "Run synthetic sync").disabled
    corrected = app.session_state["prepared-record"]
    assert corrected["submission_id"] == original["submission_id"]
    assert (
        corrected["revision"] == 2
        and corrected["content_hash"] != original["content_hash"]
    )
    next(
        item for item in app.selectbox if item.label == "Simulated transport outcome"
    ).select("success")
    button(app, "Run synthetic sync").click().run()
    assert not app.exception
    delivered = SyntheticSyncStore(root / "synthetic-sync").get(corrected)
    assert delivered["status"] == "synced" and delivered["live_synced"] is False
    if prior_outcome == "success":
        assert delivered["synthetic_id"] == receipt["synthetic_id"]


def test_post_publication_uncertainty_clears_artifact_and_reloads_actual_revision(
    tmp_path, monkeypatch
):
    if unsupported_app(tmp_path, monkeypatch):
        return
    import os
    import stat

    from edn.operations import intake

    root, store = initialise(tmp_path, monkeypatch)
    request = store.create(FIELDS, submission_id=str(uuid4()))
    app = AppTest.from_string(SCRIPT).run()
    button(app, "Approve reviewed request (self-approval)").click().run()
    button(app, "Prepare SharePoint record (dry run)").click().run()
    assert not app.exception
    app.text_input(key=f"review-{request.request_id}-1-reference").set_value(
        "PUBLISHED-BUT-UNCERTAIN"
    )
    actual_fsync = os.fsync
    parent_inode = root.stat().st_ino

    def fail_parent_durability(descriptor):
        observed = os.fstat(descriptor)
        if stat.S_ISDIR(observed.st_mode) and observed.st_ino == parent_inode:
            raise OSError("synthetic post-publication durability failure")
        return actual_fsync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(intake.os, "fsync", fail_parent_durability)
        button(app, "Save corrections").click().run()
    assert not app.exception
    assert any("unconfirmed" in item.value for item in app.error)
    assert not any("not saved" in item.value for item in app.error)
    with pytest.raises(KeyError):
        app.session_state["prepared-record"]
    actual = store.get(request.request_id)
    assert actual.revision == 2 and actual.state == "draft"
    assert actual.fields["reference"] == "PUBLISHED-BUT-UNCERTAIN"
    app.run()
    assert not app.exception
    assert (
        app.text_input(key=f"review-{request.request_id}-2-reference").value
        == "PUBLISHED-BUT-UNCERTAIN"
    )
    assert button(app, "Prepare SharePoint record (dry run)").disabled
