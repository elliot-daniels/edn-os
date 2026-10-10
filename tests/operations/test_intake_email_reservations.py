from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from edn.operations.intake import IntakeError
from edn.operations.intake_email_preview import preview_email_schedule
from edn.operations.intake_reservations import SyntheticReservationStore
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_scheduling import NOW, snapshot


def prepared(tmp_path, body=BODY):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return None
    source = email(body=body)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    requests.begin_submission()
    ledger = SyntheticReservationStore(tmp_path / "reservations.db")
    ledger.initialise()
    return drafts, source, requests, job, ledger


def reserve(data, revision=1, calendar=None):
    drafts, source, requests, _, ledger = data
    return drafts.reserve_job(
        source.identity_key,
        revision,
        requests,
        ledger,
        calendar or snapshot(),
        expected_reservation_revision=0,
        now=NOW,
    )


def test_source_hold_replay_and_concurrency_preserve_source_job_and_receipt(tmp_path):
    data = prepared(tmp_path)
    if data is None:
        return
    drafts, source, requests, job, ledger = data
    before = (drafts._backend.path.read_bytes(), requests.path.read_bytes())
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(executor.map(lambda _: reserve(data), range(2)))
    assert receipts[0] == receipts[1]
    assert ledger.list_reservations() == (receipts[0],)
    assert receipts[0]["history"][-1]["job_revision"] == job.revision
    assert (drafts._backend.path.read_bytes(), requests.path.read_bytes()) == before
    reopened = (
        type(drafts)(drafts._backend.path),
        source,
        type(requests)(requests.path),
        job,
        SyntheticReservationStore(ledger._backend.path),
    )
    assert reserve(reopened) == receipts[0]


@pytest.mark.parametrize(
    "kind", ["estimate", "stale", "pending", "cancelled", "changed", "live_calendar"]
)
def test_source_booking_refuses_unreliable_or_changed_evidence(tmp_path, kind):
    body = BODY.replace("Duration: 90 minutes", "") if kind == "estimate" else BODY
    data = prepared(tmp_path, body)
    if data is None:
        return
    drafts, source, requests, job, ledger = data
    revision = 2 if kind == "stale" else 1
    if kind == "pending":
        drafts.answer(
            source.identity_key,
            1,
            "siteLocation",
            "Different depot",
            actor="local-operator",
            requests=requests,
        )
        revision = 2
    elif kind == "cancelled":
        requests.transition(
            job.request_id, job.revision, "cancelled", reason="Synthetic cancellation"
        )
    elif kind == "changed":
        requests.update(
            job.request_id,
            job.revision,
            {**job.fields, "jobDescription": "Different scope"},
        )
    before = (
        drafts._backend.path.read_bytes(),
        requests.path.read_bytes(),
        ledger._backend.path.read_bytes(),
    )
    with pytest.raises(IntakeError):
        reserve(
            data,
            revision,
            replace(snapshot(), scope_ref="live-calendar")
            if kind == "live_calendar"
            else None,
        )
    assert (
        drafts._backend.path.read_bytes(),
        requests.path.read_bytes(),
        ledger._backend.path.read_bytes(),
    ) == before
    assert ledger.list_reservations() == ()


def test_source_explicit_night_work_is_preserved(tmp_path):
    data = prepared(
        tmp_path, BODY + "\nRequested date: 2026-10-12\nRequested time: 21:00 Adelaide"
    )
    if data is None:
        return
    drafts, source, _, job, ledger = data
    proposal = preview_email_schedule(
        drafts.get(source.identity_key), snapshot(), now=NOW, current_job=job
    )
    assert proposal.start.isoformat() == "2026-10-12T21:00:00+10:30"
    assert proposal.status == "proposal_only"
    assert "Customer requirement outside default work window" in proposal.reasons
    with pytest.raises(IntakeError, match="Reliable current source"):
        reserve(data)
    assert ledger.list_reservations() == ()


def test_mobile_source_booking_reopens_without_duplicate_or_confirmation(
    tmp_path, monkeypatch
):
    data = prepared(tmp_path)
    if data is None:
        return
    drafts, source, requests, job, ledger = data
    before = (drafts._backend.path.read_bytes(), requests.path.read_bytes())
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    app.button(key=source.identity_key + "-reserve").click().run()
    assert not app.exception
    (receipt,) = ledger.list_reservations()
    assert receipt["job_id"] == job.request_id and receipt["state"] == "provisional"
    assert any(
        "already has a verified synthetic provisional hold" in item.value
        for item in app.info
    )
    assert not any(
        button.key == source.identity_key + "-reserve" for button in app.button
    )
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert any(
        "already has a verified synthetic provisional hold" in item.value
        for item in reopened.info
    )
    assert ledger.list_reservations() == (receipt,)
    assert (drafts._backend.path.read_bytes(), requests.path.read_bytes()) == before
