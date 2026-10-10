"""Approval barrier survives a failed second-store write without stale export."""

import pytest

from edn.operations.intake import IntakeError, _ProtectedConnection
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores


def prepared(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    requests.approve(job.request_id, 1)
    return drafts, requests, source, job


def test_guarded_answer_invalidates_approval_and_refreshes_source_before_return(
    tmp_path,
):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, source, job = setup
    previous = requests.export(job.request_id, 1)
    updated = drafts.answer(
        source.identity_key,
        1,
        "siteLocation",
        "Corrected depot",
        actor="operator",
        requests=requests,
    )
    current = requests.get(job.request_id)
    assert updated["revision"] == 2 and current.state == "draft"
    assert current.source_pending and current.fields == job.fields
    assert requests.source_snapshot(job.request_id)["siteLocation"] == "Corrected depot"
    with pytest.raises(IntakeError), requests.authorise_delivery(previous):
        pytest.fail("Stale approved payload reached delivery")
    with pytest.raises(IntakeError):
        requests.approve(job.request_id, current.revision)
    resolved = requests.resolve_source_change(
        job.request_id,
        current.revision,
        decision="apply_source",
        reason="Reviewed operator answer",
    )
    requests.approve(job.request_id, resolved.revision)
    assert (
        requests.export(job.request_id, resolved.revision)["fields"][
            "Site_x002f_Location"
        ]
        == "Corrected depot"
    )
    assert any(
        "answer edit started" in (a["reason"] or "")
        for a in requests.audit_history(job.request_id)
    )


def test_interrupted_draft_publication_leaves_barrier_and_cannot_resolve_old_snapshot(
    tmp_path, monkeypatch
):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, source, job = setup
    persist = _ProtectedConnection._persist

    def interrupted(connection):
        if connection.database_name == "email-drafts.db":
            raise OSError("Synthetic source publication interruption")
        return persist(connection)

    with monkeypatch.context() as patch:
        patch.setattr(_ProtectedConnection, "_persist", interrupted)
        with pytest.raises(OSError, match="interruption"):
            drafts.answer(
                source.identity_key,
                1,
                "siteLocation",
                "Corrected depot",
                actor="operator",
                requests=requests,
            )
    assert drafts.get(source.identity_key)["revision"] == 1
    current = requests.get(job.request_id)
    assert current.source_pending and current.state == "draft"
    with pytest.raises(IntakeError, match="Refresh"):
        requests.resolve_source_change(
            job.request_id,
            current.revision,
            decision="keep_local",
            reason="Cannot clear unverified old source",
        )
    with pytest.raises(IntakeError):
        requests.approve(job.request_id, current.revision)
    # Explicit recovery rereads the current unchanged draft under its lock.
    recovered = drafts.materialise(source.identity_key, 1, requests)
    assert recovered.source_pending
    resolved = requests.resolve_source_change(
        job.request_id,
        recovered.revision,
        decision="keep_local",
        reason="Reviewed unchanged source after interruption",
    )
    assert resolved.state == "draft" and not resolved.source_pending


def test_invalid_guarded_field_keeps_both_stores_and_approval_unchanged(tmp_path):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, source, job = setup
    before = (drafts.get(source.identity_key), requests.get(job.request_id))
    with pytest.raises(IntakeError, match="phone"):
        drafts.answer(
            source.identity_key,
            1,
            "phone",
            "invalid",
            actor="operator",
            requests=requests,
        )
    assert (drafts.get(source.identity_key), requests.get(job.request_id)) == before


def test_terminal_job_cannot_be_changed_by_guarded_answer(tmp_path):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, source, job = setup
    requests.transition(
        job.request_id, 1, "cancelled", reason="Synthetic cancellation"
    )
    with pytest.raises(IntakeError, match="Reopen"):
        drafts.answer(
            source.identity_key,
            1,
            "siteLocation",
            "Another depot",
            actor="operator",
            requests=requests,
        )
    assert drafts.get(source.identity_key)["revision"] == 1
