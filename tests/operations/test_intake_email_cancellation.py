from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, _ProtectedConnection
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores


def prepared(tmp_path, **changes):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    original = email(body=BODY)
    drafts.ingest(original)
    job = drafts.materialise(original.identity_key, 1, requests)
    requests.approve(job.request_id, job.revision)
    message = email(
        subject="Cancel the job", body=BODY, external_id="cancel-1", **changes
    )
    source = drafts.ingest(message)
    return drafts, requests, original, requests.get(job.request_id), message, source


def test_cancellation_invalidates_approval_retains_source_and_replays_once(tmp_path):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, original, job, message, source = setup
    payload = requests.export(job.request_id, job.revision)
    cancelled = drafts.cancel_job(message.identity_key, 1, requests)
    assert cancelled.state == "cancelled" and cancelled.revision == job.revision + 1
    assert cancelled.approved_revision is None and cancelled.sync_status == "not_synced"
    assert cancelled.fields == job.fields and cancelled.attachments == job.attachments
    history = requests.audit_history(job.request_id)
    assert history[-1]["decision"] == "cancelled"
    assert message.identity_key in history[-1]["reason"]
    assert source["source_hash"] in history[-1]["reason"]
    assert "uid=" in history[-1]["actor"]
    assert drafts.get(message.identity_key) == source
    assert drafts.get(original.identity_key)["original"]["body"] == BODY
    assert drafts.cancel_job(message.identity_key, 1, requests) == cancelled
    assert requests.audit_history(job.request_id) == history
    with pytest.raises(IntakeError), requests.authorise_delivery(payload):
        pytest.fail("Cancelled job reached delivery")


def test_concurrent_cancellation_has_one_durable_audit(tmp_path):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, _, job, message, _ = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda _: drafts.cancel_job(message.identity_key, 1, requests), range(2)
            )
        )
    assert outcomes[0] == outcomes[1]
    assert requests.get(job.request_id) == outcomes[0]
    assert (
        sum(
            row["decision"] == "cancelled"
            for row in requests.audit_history(job.request_id)
        )
        == 1
    )


@pytest.mark.parametrize(
    "condition", ["ambiguous", "source_pending", "malformed", "missing", "stale"]
)
def test_uncertain_targets_do_not_cancel_or_hide_corrupt_rows(tmp_path, condition):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, original, job, message, _ = setup
    revision = 1
    if condition in {"ambiguous", "malformed"}:
        second = requests.create(job.fields, submission_id=str(uuid4()))
        if condition == "malformed":
            with requests._connect() as connection:
                connection.execute(
                    "UPDATE intake_requests SET fields='{}' WHERE request_id=?",
                    (second.request_id,),
                )
    elif condition == "source_pending":
        drafts.answer(
            original.identity_key,
            1,
            "siteLocation",
            "Changed depot",
            actor="operator",
            requests=requests,
        )
    elif condition == "missing":
        message = email(
            subject="Cancel the job",
            body="Site: Synthetic depot",
            external_id="incomplete-cancel",
        )
        drafts.ingest(message)
    else:
        revision = 2
    before = requests.get(job.request_id)
    with pytest.raises(IntakeError):
        drafts.cancel_job(message.identity_key, revision, requests)
    assert requests.get(job.request_id) == before
    assert not any(
        row["decision"] == "cancelled" for row in requests.audit_history(job.request_id)
    )


@pytest.mark.parametrize(
    "changes", [{"source": "outlook"}, {"subject": "Remittance advice"}]
)
def test_real_or_ordinary_email_cannot_cancel(tmp_path, changes):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, _, job, message, _ = setup
    values = {"source": message.source, "subject": message.subject, **changes}
    other = email(body=BODY, external_id="other", **values)
    drafts.ingest(other)
    with pytest.raises(IntakeError, match="Only synthetic cancellation"):
        drafts.cancel_job(other.identity_key, 1, requests)
    assert requests.get(job.request_id) == job


def test_failed_publication_retries_without_duplicate_cancellation(
    tmp_path, monkeypatch
):
    setup = prepared(tmp_path)
    if setup is None:
        return
    drafts, requests, _, job, message, _ = setup
    persist = _ProtectedConnection._persist

    def fail(connection):
        if connection.database_name == "requests.db":
            raise RuntimeError("Synthetic publication failure")
        return persist(connection)

    with monkeypatch.context() as patch:
        patch.setattr(_ProtectedConnection, "_persist", fail)
        with pytest.raises(RuntimeError, match="publication failure"):
            drafts.cancel_job(message.identity_key, 1, requests)
    assert requests.get(job.request_id) == job
    result = drafts.cancel_job(message.identity_key, 1, requests)
    assert result.state == "cancelled"
    assert drafts.cancel_job(message.identity_key, 1, requests) == result
