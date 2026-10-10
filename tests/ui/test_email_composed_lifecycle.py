"""One composed synthetic lifecycle; upload uses the real handler, not a picker."""

import pytest
from streamlit.testing.v1 import AppTest

from edn.operations.intake import IntakeError
from edn.operations.intake_attachments import IntakeAttachmentStore
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.operations.intake_sync import SyntheticSyncStore
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_updates import UPDATE
from tests.ui.test_email_job_evidence_journey import button, setup


def test_composed_email_evidence_sync_hold_cancel_release_and_reopen(
    tmp_path, monkeypatch
):
    content = b"Fictional complete lifecycle evidence\n"
    data = setup(tmp_path, monkeypatch, content)
    if data is None:
        return
    view, requests, drafts, source, initial, script = data
    original = drafts.get(source.identity_key)
    button(view, "Save supporting file")
    button(view, "Approve reviewed request (self-approval)")
    button(view, "Prepare SharePoint record (dry run)")
    payload = requests.export(initial.request_id, 2)
    button(view, "Run synthetic sync")
    sync = SyntheticSyncStore(tmp_path / "synthetic-sync", intake_store=requests)
    delivered = sync.get(payload)
    assert delivered["status"] == "synced"
    assert payload["not_synced"] is True and payload["dry_run"] is True
    assert any("live SharePoint: not synced" in item.value for item in view.caption)
    view.button(key=source.identity_key + "-reserve").click().run()
    assert not view.exception
    ledger = SyntheticReservationStore(tmp_path / "reservations.db")
    (hold,) = ledger.list_reservations()
    assert hold["state"] == "provisional" and hold["history"][-1]["job_revision"] == 2
    cancellation = email(
        subject="Cancel the job", body=UPDATE, external_id="lifecycle-cancel"
    )
    retained_cancel = drafts.ingest(cancellation)
    view = AppTest.from_file(str(script)).run()
    view.checkbox(key=cancellation.identity_key + "-confirm-cancel").check().run()
    view.button(key=cancellation.identity_key + "-apply-action").click().run()
    assert not view.exception
    cancelled = requests.get(initial.request_id)
    assert cancelled.state == "cancelled" and cancelled.revision == 3
    assert ledger.list_reservations() == (hold,)
    with pytest.raises(IntakeError), requests.authorise_delivery(payload):
        pytest.fail("Cancelled job authorised stale delivery")
    assert any("Scheduling is blocked" in item.value for item in view.error)
    next(
        c
        for c in view.checkbox
        if c.label == "Confirm release of this stale synthetic hold"
    ).check().run()
    button(view, "Release stale synthetic hold")
    (released,) = ledger.list_reservations()
    assert released["state"] == "cancelled" and released["revision"] == 2
    assert released["history"][:-1] == hold["history"]
    assert sync.get(payload) == delivered  # Retained historical synthetic outcome.
    assert drafts.get(source.identity_key) == original
    assert drafts.get(cancellation.identity_key) == retained_cancel
    (attachment,) = cancelled.attachments
    files = IntakeAttachmentStore(tmp_path / "attachments")
    assert files.read(cancelled.request_id, attachment["attachment_id"]) == content
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert any("Synthetic hold released" in item.value for item in reopened.info)
    assert requests.get(cancelled.request_id) == cancelled
    assert ledger.list_reservations() == (released,)
    assert sync.get(payload) == delivered
    assert files.read(cancelled.request_id, attachment["attachment_id"]) == content
