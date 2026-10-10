"""Explicit synthetic API orchestration, not an unattended execution claim."""

from edn.operations.intake_email import assess_email
from edn.operations.intake_email_reconciliation import match_email_job
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.operations.intake_scheduling import DurationEstimate, SchedulingRequest
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_reservations import store as reservation_store
from tests.operations.test_intake_scheduling import NOW, snapshot


def test_canonical_job_match_and_explicit_synthetic_reservation_reopen(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    ledger = reservation_store(tmp_path)
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    assert drafts.materialise(source.identity_key, 1, requests) == job
    proposals = []
    for native_id in ("original-forward", "recipient-replay"):
        repeated = email(body=BODY, external_id=native_id)
        proposal = match_email_job(
            repeated, assess_email(repeated), requests.list_requests(), complete=True
        )
        assert proposal.status == "matched_proposal"
        assert proposal.target_id == job.request_id
        assert proposal.target_revision == job.revision
        assert proposal.source_key == repeated.identity_key
        proposals.append(proposal)
    assert proposals[0].target_hash == proposals[1].target_hash
    assert proposals[0].source_key != proposals[1].source_key
    request = SchedulingRequest(
        job.request_id,
        DurationEstimate(90, "Explicit synthetic source duration", True),
        True,
    )
    kwargs = dict(
        job_revision=job.revision,
        job_hash=proposals[0].target_hash,
        expected_revision=0,
        now=NOW,
        actor="synthetic-operator",
    )
    receipt = ledger.reserve(request, snapshot(), **kwargs)
    assert receipt["state"] == "provisional"
    assert receipt["history"][0]["job_hash"] == proposals[0].target_hash
    reopened = SyntheticReservationStore(tmp_path / "reservations.db")
    assert reopened.reserve(request, snapshot(), **kwargs) == receipt
    assert reopened.list_reservations() == (receipt,)
    assert requests.list_requests() == (job,)
    ordinary = email(subject="Remittance advice", body="Synthetic payment notice")
    assert (
        match_email_job(
            ordinary, assess_email(ordinary), requests.list_requests(), complete=True
        ).status
        == "not_applicable"
    )
    assert reopened.list_reservations() == (receipt,)
