"""Synthetic sync failure/unknown recovery across fresh app sessions."""

from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from edn.operations.intake_attachments import IntakeAttachmentStore
from edn.operations.intake_sync import SyntheticSyncStore
from tests.ui.test_email_job_evidence_journey import button, setup


@pytest.mark.parametrize("outcome", ["failed", "unknown"])
def test_email_sync_recovery_after_reopen_is_honest_and_does_not_duplicate(
    tmp_path, monkeypatch, outcome
):
    content = b"Fictional recovery evidence\n"
    data = setup(tmp_path, monkeypatch, content)
    if data is None:
        return
    view, requests, drafts, source, initial, script = data
    original = drafts.get(source.identity_key)
    button(view, "Save supporting file")
    button(view, "Approve reviewed request (self-approval)")
    button(view, "Prepare SharePoint record (dry run)")
    payload = deepcopy(view.session_state["prepared-record"])
    next(s for s in view.selectbox if s.label == "Simulated transport outcome").select(
        outcome
    )
    button(view, "Run synthetic sync")
    sync = SyntheticSyncStore(tmp_path / "synthetic-sync", intake_store=requests)
    prior = sync.get(payload)
    assert prior["status"] == outcome and prior["attempt"] == 1
    assert any(
        f"Synthetic transport: {outcome}" in item.value for item in view.markdown
    )
    assert any("live SharePoint: not synced" in item.value for item in view.markdown)
    assert next(b for b in view.button if b.label == "Run synthetic sync").disabled is (
        outcome == "unknown"
    )
    history = requests.audit_history(initial.request_id)
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    button(reopened, "Prepare SharePoint record (dry run)")
    recovered_payload = deepcopy(reopened.session_state["prepared-record"])
    assert recovered_payload == payload
    assert sync.get(recovered_payload) == prior
    assert any(
        f"Synthetic transport: {outcome}" in item.value for item in reopened.markdown
    )
    if outcome == "unknown":
        assert next(
            b for b in reopened.button if b.label == "Run synthetic sync"
        ).disabled
        button(reopened, "Reconcile synthetic attempt")
    else:
        assert not next(
            b for b in reopened.button if b.label == "Run synthetic sync"
        ).disabled
        next(
            s for s in reopened.selectbox if s.label == "Simulated transport outcome"
        ).select("success")
        button(reopened, "Run synthetic sync")
    confirmed = sync.get(payload)
    assert confirmed["status"] == "synced"
    assert confirmed["attempt"] == (1 if outcome == "unknown" else 2)
    assert payload["not_synced"] is True and payload["dry_run"] is True
    assert any(
        "live SharePoint: not synced" in item.value for item in reopened.markdown
    )
    assert requests.audit_history(initial.request_id) == history
    assert drafts.get(source.identity_key) == original
    request = requests.get(initial.request_id)
    assert request.state == "approved" and request.revision == 2
    (attachment,) = request.attachments
    files = IntakeAttachmentStore(tmp_path / "attachments")
    assert files.read(request.request_id, attachment["attachment_id"]) == content
    final = AppTest.from_file(str(script)).run()
    assert not final.exception
    button(final, "Prepare SharePoint record (dry run)")
    assert sync.get(final.session_state["prepared-record"]) == confirmed
    button(final, "Run synthetic sync")
    assert sync.get(payload) == confirmed  # Exact replay is not another attempt.
