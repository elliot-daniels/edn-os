from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, _digest, _ProtectedConnection
from edn.operations.intake_reservations import SyntheticReservationStore
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_scheduling import NOW, request, snapshot


def prepared(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    ledger = SyntheticReservationStore(tmp_path / "reservations.db")
    ledger.initialise()
    return drafts, source, requests, job, ledger


def reserve(requests, job, ledger, **kwargs):
    arguments = dict(
        job_revision=job.revision,
        job_hash=_digest(job.fields, job.attachments),
        expected_revision=0,
        now=NOW,
        actor="synthetic-operator",
    )
    arguments.update(kwargs)
    return ledger.reserve_for_job(
        replace(request(), job_id=job.request_id), snapshot(), requests, **arguments
    )


def test_canonical_hold_replay_reopen_preserves_job_and_audit(tmp_path):
    data = prepared(tmp_path)
    if data is None:
        return
    _, _, requests, job, ledger = data
    before = requests.path.read_bytes()
    receipt = reserve(requests, job, ledger)
    assert receipt["history"][-1]["job_hash"] == _digest(job.fields, job.attachments)
    reopened = SyntheticReservationStore(ledger._backend.path)
    assert reserve(requests, job, reopened) == receipt
    assert requests.path.read_bytes() == before
    assert receipt["state"] == "provisional"


@pytest.mark.parametrize(
    "kind", ["edit", "cancelled", "rejected", "alias", "pending", "hash"]
)
def test_unverified_canonical_version_never_publishes_hold(tmp_path, kind):
    data = prepared(tmp_path)
    if data is None:
        return
    drafts, source, requests, job, ledger = data
    arguments = {}
    if kind == "edit":
        requests.update(
            job.request_id, job.revision, {**job.fields, "jobDescription": "Changed"}
        )
    elif kind in {"cancelled", "rejected"}:
        requests.transition(
            job.request_id, job.revision, kind, reason="Synthetic terminal test"
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
    elif kind == "pending":
        drafts.answer(
            source.identity_key,
            1,
            "siteLocation",
            "Changed depot",
            actor="local-operator",
            requests=requests,
        )
    else:
        arguments["job_hash"] = "a" * 64
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    with pytest.raises(IntakeError):
        reserve(requests, job, ledger, **arguments)
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before
    assert ledger.list_reservations() == ()


def test_requested_date_cannot_be_dropped_by_caller(tmp_path):
    data = prepared(tmp_path)
    if data is None:
        return
    _, _, requests, job, ledger = data
    job = requests.update(
        job.request_id, job.revision, {**job.fields, "preferredDate": "2026-10-12"}
    )
    with pytest.raises(IntakeError, match="requested date"):
        reserve(requests, job, ledger)
    receipt = ledger.reserve_for_job(
        replace(request(requested_date=date(2026, 10, 12)), job_id=job.request_id),
        snapshot(),
        requests,
        job_revision=job.revision,
        job_hash=_digest(job.fields, job.attachments),
        expected_revision=0,
        now=NOW,
        actor="synthetic-operator",
    )
    assert receipt["history"][-1]["plan"]["start"].startswith("2026-10-12")


def test_concurrent_canonical_jobs_hold_distinct_buffered_intervals(tmp_path):
    data = prepared(tmp_path)
    if data is None:
        return
    _, _, requests, job, ledger = data
    other = requests.create(
        {**job.fields, "reference": "SYNTH-OTHER"}, submission_id=str(uuid4())
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(
            executor.map(lambda item: reserve(requests, item, ledger), (job, other))
        )
    plans = sorted(
        (item["history"][-1]["plan"] for item in receipts),
        key=lambda item: item["occupied_start"],
    )
    assert plans[0]["occupied_end"] <= plans[1]["occupied_start"]
    assert (
        requests.get(job.request_id) == job and requests.get(other.request_id) == other
    )


def test_reservation_publication_failure_preserves_job_and_retry(tmp_path, monkeypatch):
    data = prepared(tmp_path)
    if data is None:
        return
    _, _, requests, job, ledger = data
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    persist = _ProtectedConnection._persist

    def fail(connection):
        if connection.database_name == "reservations.db":
            raise RuntimeError("Synthetic reservation publication failure")
        return persist(connection)

    with monkeypatch.context() as patch:
        patch.setattr(_ProtectedConnection, "_persist", fail)
        with pytest.raises(RuntimeError):
            reserve(requests, job, ledger)
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before
    assert ledger.list_reservations() == ()
    receipt = reserve(requests, job, ledger)
    assert reserve(requests, job, ledger) == receipt
    assert requests.get(job.request_id) == job
