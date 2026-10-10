from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, _digest
from edn.operations.intake_reservation_calendar import include_local_reservations
from tests.operations.test_intake_reservation_calendar import setup
from tests.operations.test_intake_scheduling import NOW, snapshot


def release(requests, job, ledger, revision):
    return ledger.release_stale_for_job(
        requests,
        job.request_id,
        job_revision=job.revision,
        job_hash=_digest(job.fields, job.attachments),
        expected_revision=revision,
        actor="synthetic-operator",
        now=NOW,
    )


@pytest.mark.parametrize("kind", ["edit", "cancelled", "rejected", "pending"])
def test_stale_hold_release_restores_availability_preserves_all_history(tmp_path, kind):
    data = setup(tmp_path)
    if data is None:
        return
    drafts, requests, job, ledger, receipt = data
    if kind == "edit":
        job = requests.update(
            job.request_id,
            job.revision,
            {**job.fields, "jobDescription": "Different scope"},
        )
    elif kind in {"cancelled", "rejected"}:
        job = requests.transition(
            job.request_id, job.revision, kind, reason="Synthetic terminal action"
        )
    else:
        (source,) = drafts.list_drafts()[0]
        drafts.answer(
            source["source_key"],
            1,
            "siteLocation",
            "Different site",
            actor="local-operator",
            requests=requests,
        )
        job = requests.get(job.request_id)
    with pytest.raises(IntakeError):
        include_local_reservations(snapshot(), ledger, requests)
    before = (requests.path.read_bytes(), drafts._backend.path.read_bytes())
    result = release(requests, job, ledger, receipt["revision"])
    assert result["state"] == "cancelled" and result["revision"] == 2
    assert result["history"][:-1] == receipt["history"]
    last = result["history"][-1]
    assert (
        last["action"] == "cancelled"
        and _digest(job.fields, job.attachments) in last["reason"]
    )
    assert last["plan"] == receipt["history"][-1]["plan"]
    assert include_local_reservations(snapshot(), ledger, requests).events == ()
    assert release(requests, job, ledger, result["revision"]) == result
    assert (requests.path.read_bytes(), drafts._backend.path.read_bytes()) == before


@pytest.mark.parametrize("kind", ["matching", "old_job", "old_ledger", "alias"])
def test_unverified_or_matching_hold_never_releases(tmp_path, kind):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, job, ledger, receipt = data
    revision = receipt["revision"]
    if kind == "old_job":
        requests.update(
            job.request_id, job.revision, {**job.fields, "jobDescription": "Changed"}
        )
    elif kind == "old_ledger":
        job = requests.update(
            job.request_id, job.revision, {**job.fields, "jobDescription": "Changed"}
        )
        ledger.cancel(
            job.request_id,
            revision,
            actor="synthetic-operator",
            reason="Prior release",
            now=NOW,
        )
    elif kind == "alias":
        other = requests.create(job.fields, submission_id=str(uuid4()))
        requests.resolve_duplicate(
            job.request_id,
            other.request_id,
            job.revision,
            decision="same_work",
            reason="Synthetic duplicate",
        )
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    with pytest.raises(IntakeError):
        release(requests, job, ledger, revision)
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before
