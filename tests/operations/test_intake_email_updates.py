from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, _ProtectedConnection
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores

UPDATE = (
    "Customer: Synthetic Co\nSite: Synthetic depot\nJob reference: SYNTH-123\n"
    "Scope: Replace two failed switches"
)


def prepared(tmp_path, body=UPDATE):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    original = email(body=BODY)
    drafts.ingest(original)
    job = drafts.materialise(original.identity_key, 1, requests)
    job = requests.approve(job.request_id, job.revision)
    values = dict(subject="Job update", body=body, external_id="update-1")
    message = email(**values)
    source = drafts.ingest(message)
    return drafts, requests, job, message, source


def test_update_invalidates_approval_preserves_original_and_replays_without_rollback(
    tmp_path,
):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, job, message, source = setup
    old = requests.export(job.request_id, job.revision)
    changed = drafts.update_job(message.identity_key, 1, requests)
    assert changed.revision == job.revision + 1 and changed.state == "draft"
    assert changed.fields == {
        **job.fields,
        "jobDescription": "Replace two failed switches",
    }
    assert changed.approved_revision is None and changed.attachments == job.attachments
    assert drafts.get(message.identity_key) == source
    history = requests.audit_history(job.request_id)
    assert history[-1]["decision"] == "edited_approval_invalidated"
    assert (
        message.identity_key in history[-1]["reason"]
        and source["source_hash"] in history[-1]["reason"]
    )
    assert "uid=" in history[-1]["actor"]
    with pytest.raises(IntakeError), requests.authorise_delivery(old):
        pytest.fail("Stale approval reached delivery")
    corrected = requests.update(
        job.request_id,
        changed.revision,
        {**changed.fields, "jobDescription": "Operator corrected scope"},
    )
    assert drafts.update_job(message.identity_key, 1, requests) == corrected
    assert requests.get(job.request_id) == corrected
    assert len(requests.audit_history(job.request_id)) == len(history) + 1
    cancelled = requests.transition(
        job.request_id,
        corrected.revision,
        "cancelled",
        reason="Synthetic operator cancellation",
    )
    assert drafts.update_job(message.identity_key, 1, requests) == cancelled


def test_concurrent_update_records_one_revision(tmp_path):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, job, message, _ = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda _: drafts.update_job(message.identity_key, 1, requests), range(2)
            )
        )
    assert outcomes[0] == outcomes[1]
    assert outcomes[0].revision == job.revision + 1


@pytest.mark.parametrize(
    "suffix",
    [
        "\nRequested time: 22:00 Adelaide",
        "\nDuration: 90 minutes",
        "\nEquipment: switch",
        "\nAccess: escort needed",
        "\nRequested date: next Tuesday",
        "\nEmail: not-an-address",
    ],
)
def test_unsupported_or_invalid_update_facts_leave_job_unchanged(tmp_path, suffix):
    setup = prepared(tmp_path, body=UPDATE + suffix)
    if setup is None:
        return
    drafts, requests, job, message, _ = setup
    with pytest.raises(IntakeError):
        drafts.update_job(message.identity_key, 1, requests)
    assert requests.get(job.request_id) == job


@pytest.mark.parametrize(
    "condition",
    ["ambiguous", "malformed", "stale", "terminal", "real", "ordinary", "attachment"],
)
def test_uncertain_sources_targets_and_evidence_require_review(tmp_path, condition):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, job, message, _ = setup
    revision = 1
    if condition in {"ambiguous", "malformed"}:
        second = requests.create(job.fields, submission_id=str(uuid4()))
        if condition == "malformed":
            with requests._connect() as connection:
                connection.execute(
                    "UPDATE intake_revisions SET fields='{}' WHERE request_id=?",
                    (second.request_id,),
                )
    elif condition == "stale":
        revision = 2
    elif condition == "terminal":
        job = requests.transition(
            job.request_id, job.revision, "cancelled", reason="Synthetic cancellation"
        )
    else:
        values = (
            {"source": "outlook"}
            if condition == "real"
            else (
                {"subject": "Remittance advice"}
                if condition == "ordinary"
                else {"attachments": ({"name": "evidence.txt"},)}
            )
        )
        message = email(
            body=UPDATE,
            subject=values.pop("subject", "Job update"),
            external_id="other",
            **values,
        )
        drafts.ingest(message)
    before = requests.get(job.request_id)
    with pytest.raises(IntakeError):
        drafts.update_job(message.identity_key, revision, requests)
    assert requests.get(job.request_id) == before


def test_iso_requested_date_is_preserved_without_booking(tmp_path):
    setup = prepared(tmp_path, body=UPDATE + "\nRequested date: 2026-10-14")
    if setup is None:
        return
    drafts, requests, job, message, _ = setup
    changed = drafts.update_job(message.identity_key, 1, requests)
    assert changed.fields["preferredDate"] == "2026-10-14"
    assert changed.request_id == job.request_id
    assert changed.sync_status == "not_synced"


def test_failed_update_publication_is_retryable(tmp_path, monkeypatch):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, job, message, _ = setup
    persist = _ProtectedConnection._persist

    def fail(connection):
        if connection.database_name == "requests.db":
            raise RuntimeError("Synthetic update publication failure")
        return persist(connection)

    with monkeypatch.context() as patch:
        patch.setattr(_ProtectedConnection, "_persist", fail)
        with pytest.raises(RuntimeError):
            drafts.update_job(message.identity_key, 1, requests)
    assert requests.get(job.request_id) == job
    changed = drafts.update_job(message.identity_key, 1, requests)
    assert drafts.update_job(message.identity_key, 1, requests) == changed
