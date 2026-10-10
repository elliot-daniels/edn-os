"""Composed synthetic email job journey through the existing upload handler.

AppTest does not drive a physical browser file picker. A synthetic upload object
feeds the actual file-uploader handler; all store/validation/approval code is real.
"""

import hashlib
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from edn.operations.intake import IntakeError, IntakeStore
from edn.operations.intake_attachments import IntakeAttachmentStore
from edn.operations.intake_security import AnchoredDirectory
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores


class SyntheticUpload:
    name = "supporting-evidence.txt"

    def __init__(self, payload):
        self.payload = payload

    def getvalue(self):
        return self.payload


def button(app, label):
    matches = [item for item in app.button if item.label == label]
    assert len(matches) == 1
    matches[0].click().run()
    assert not app.exception


def setup(tmp_path, monkeypatch, payload):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    # Match the launcher's explicit private bootstrap, not just its DB fixture.
    with AnchoredDirectory(tmp_path) as root:
        with root.child("attachments", create=True):
            pass
        with root.child("synthetic-sync", create=True):
            pass
    source = email(body=BODY)
    drafts.ingest(source)
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    original_widget = st.file_uploader

    def synthetic_widget(label, *args, **kwargs):
        actual = original_widget(label, *args, **kwargs)
        if label == "Supporting document or photo":
            return SyntheticUpload(payload)
        return actual

    monkeypatch.setattr(st, "file_uploader", synthetic_widget)
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    app.button(key=source.identity_key + "-materialise").click().run()
    assert not app.exception
    (request,) = requests.list_requests()
    reader = IntakeStore(requests.path, evidence_root=tmp_path / "attachments")
    return app, reader, drafts, source, request, script


def test_email_job_upload_approval_export_correction_and_fresh_application(
    tmp_path, monkeypatch
):
    content = b"Synthetic supporting evidence\n"
    prepared = setup(tmp_path, monkeypatch, content)
    if prepared is None:
        return
    app, requests, drafts, source, initial, script = prepared
    original = drafts.get(source.identity_key)
    button(app, "Save supporting file")
    request = requests.get(initial.request_id)
    assert request.revision == 2 and len(request.attachments) == 1
    manifest = request.attachments
    (metadata,) = manifest
    assert metadata["request_id"] == request.request_id
    assert metadata["sha256"] == hashlib.sha256(content).hexdigest()
    files = IntakeAttachmentStore(tmp_path / "attachments")
    assert files.read(request.request_id, metadata["attachment_id"]) == content
    button(app, "Approve reviewed request (self-approval)")
    assert requests.get(request.request_id).state == "approved"
    button(app, "Prepare SharePoint record (dry run)")
    exported = requests.export(request.request_id, 2)
    assert exported["fields"]["Source"] == "EDN OS Email"
    assert exported["attachment_manifest"] == manifest
    assert (
        exported["source_provenance"]["email_receipt"]["source_hash"]
        == original["source_hash"]
    )
    assert exported["sync_status"] == "dry_run" and exported["dry_run"] is True

    # An identical upload is a replay; it must not consume another revision or
    # silently revoke an unchanged exact-content approval.
    button(app, "Save supporting file")
    replay = requests.get(request.request_id)
    assert replay.revision == 2 and replay.state == "approved"
    assert replay.attachments == manifest

    key = source.identity_key
    app.selectbox(key=key + "-field").select("siteLocation")
    app.text_input(key=key + "-answer").input("Corrected synthetic depot")
    app.button(key=key + "-save").click().run()
    assert not app.exception
    changed = requests.get(request.request_id)
    assert changed.state == "draft" and changed.source_pending
    assert changed.attachments == manifest
    with pytest.raises(IntakeError), requests.authorise_delivery(exported):
        pytest.fail("Stale payload was authorised")
    assert drafts.get(key)["original"] == original["original"]

    resolutions = [item for item in app.selectbox if item.label == "Source resolution"]
    resolutions[0].select("apply_source")
    reasons = [
        item for item in app.text_input if item.label == "Reason for source resolution"
    ]
    reasons[0].input("Reviewed corrected synthetic site; evidence preserved")
    button(app, "Resolve changed source")
    button(app, "Approve reviewed request (self-approval)")
    button(app, "Prepare SharePoint record (dry run)")
    current = requests.get(request.request_id)
    updated = requests.export(current.request_id, current.revision)
    assert updated["fields"]["Site_x002f_Location"] == "Corrected synthetic depot"
    assert updated["attachment_manifest"] == manifest
    assert updated["idempotency_key"] == exported["idempotency_key"]
    assert updated["content_hash"] != exported["content_hash"]
    # The explicit export above records dry-run preparation and updated_at.
    # Compare restart against the state after the final intentional mutation.
    current = requests.get(current.request_id)
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    persisted = IntakeStore(requests.path, evidence_root=tmp_path / "attachments").get(
        current.request_id
    )
    assert persisted == current and persisted.state == "approved"
    assert files.read(current.request_id, metadata["attachment_id"]) == content
    assert any("supporting-evidence.txt" in item.value for item in reopened.text)


def test_empty_upload_does_not_change_canonical_email_job(tmp_path, monkeypatch):
    prepared = setup(tmp_path, monkeypatch, b"")
    if prepared is None:
        return
    app, requests, drafts, source, initial, _ = prepared
    button(app, "Save supporting file")
    assert app.error
    assert requests.get(initial.request_id) == initial
    assert drafts.get(source.identity_key)["revision"] == 1
