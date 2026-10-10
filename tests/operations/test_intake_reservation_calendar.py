from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from edn.operations.intake import IntakeError, _digest
from edn.operations.intake_reservation_calendar import include_local_reservations
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.operations.intake_scheduling import propose_schedule
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_scheduling import NOW, request, snapshot


def setup(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    # The full app creates this durable manual-entry intent on first render.
    # Establish it before measuring the read-only reservation projection.
    requests.begin_submission()
    ledger = SyntheticReservationStore(tmp_path / "reservations.db")
    ledger.initialise()
    receipt = ledger.reserve(
        replace(request(), job_id=job.request_id),
        snapshot(),
        job_revision=job.revision,
        job_hash=_digest(job.fields, job.attachments),
        expected_revision=0,
        now=NOW,
        actor="synthetic-operator",
    )
    return drafts, requests, job, ledger, receipt


def test_verified_hold_blocks_buffers_and_cancelled_hold_releases_snapshot(tmp_path):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, job, ledger, receipt = data
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    projected = include_local_reservations(snapshot(), ledger, requests)
    assert len(projected.events) == 1
    next_plan = propose_schedule(
        replace(request(), job_id=str(uuid4())), projected, now=NOW
    )
    assert next_plan.occupied_start >= projected.events[0].end
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before
    ledger.cancel(
        job.request_id,
        receipt["revision"],
        actor="synthetic-operator",
        reason="Synthetic release",
        now=NOW,
    )
    assert include_local_reservations(snapshot(), ledger, requests).events == ()
    assert len(ledger.list_reservations()[0]["history"]) == 2


@pytest.mark.parametrize(
    "kind", ["edit", "cancelled", "rejected", "alias", "corrupt", "wrong_hash"]
)
def test_unverified_binding_blocks_availability_without_mutation(tmp_path, kind):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, job, ledger, _ = data
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
    elif kind == "corrupt":
        with requests._connect() as connection:
            connection.execute(
                "UPDATE intake_revisions SET fields='{}' WHERE request_id=?",
                (job.request_id,),
            )
    else:
        with ledger._backend._connect() as connection:
            connection.execute(
                "UPDATE reservations SET record=replace(record,?,?)",
                (_digest(job.fields, job.attachments), "a" * 64),
            )
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    with pytest.raises(IntakeError):
        include_local_reservations(snapshot(), ledger, requests)
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before


def test_mobile_corrupt_ledger_never_falls_back_to_empty_calendar(
    tmp_path, monkeypatch
):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, _, ledger, _ = data
    with ledger._backend._connect() as connection:
        connection.execute("UPDATE reservations SET record='{}'")
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    assert any("Scheduling is blocked" in item.value for item in app.error)
    assert not any(
        "Provisional — Awaiting Confirmation" in item.value for item in app.markdown
    )
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before


def test_mobile_retained_hold_is_visible_without_second_proposal(tmp_path, monkeypatch):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, job, ledger, _ = data
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    assert any(
        "already has a verified synthetic provisional hold" in item.value
        for item in app.info
    )
    assert any(
        job.request_id in item.value and "occupancy" in item.value for item in app.text
    )
    assert not any(
        "Provisional — Awaiting Confirmation" in item.value for item in app.markdown
    )
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before
