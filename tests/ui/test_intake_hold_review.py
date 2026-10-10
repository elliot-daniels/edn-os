from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.operations.test_intake_reservation_calendar import setup


def app(tmp_path, monkeypatch):
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    return AppTest.from_file(str(script)).run()


@pytest.mark.parametrize("terminal", [False, True])
def test_mobile_stale_hold_release_preserves_history_and_reopens(
    tmp_path, monkeypatch, terminal
):
    data = setup(tmp_path)
    if data is None:
        return
    drafts, requests, job, ledger, receipt = data
    if terminal:
        job = requests.transition(
            job.request_id, job.revision, "cancelled", reason="Synthetic cancellation"
        )
    else:
        job = requests.update(
            job.request_id,
            job.revision,
            {**job.fields, "jobDescription": "Changed scope"},
        )
    before = (requests.path.read_bytes(), drafts._backend.path.read_bytes())
    view = app(tmp_path, monkeypatch)
    assert not view.exception
    (button,) = [b for b in view.button if b.label == "Release stale synthetic hold"]
    assert button.disabled
    (check,) = [
        c
        for c in view.checkbox
        if c.label == "Confirm release of this stale synthetic hold"
    ]
    check.check().run()
    next(
        b for b in view.button if b.label == "Release stale synthetic hold"
    ).click().run()
    assert not view.exception
    (released,) = ledger.list_reservations()
    assert released["state"] == "cancelled" and released["revision"] == 2
    assert released["history"][:-1] == receipt["history"]
    assert any("Synthetic hold released" in item.value for item in view.info)
    reopened = app(tmp_path, monkeypatch)
    assert not reopened.exception
    assert any("Synthetic hold released" in item.value for item in reopened.info)
    assert ledger.list_reservations() == (released,)
    assert (requests.path.read_bytes(), drafts._backend.path.read_bytes()) == before


def test_matching_hold_has_no_release_control(tmp_path, monkeypatch):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, _, ledger, _ = data
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    view = app(tmp_path, monkeypatch)
    assert not view.exception
    assert not any(b.label == "Release stale synthetic hold" for b in view.button)
    assert any("Current matching hold" in item.value for item in view.info)
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before


def test_changed_job_invalidates_checked_release_confirmation(tmp_path, monkeypatch):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, job, ledger, _ = data
    job = requests.update(
        job.request_id, job.revision, {**job.fields, "jobDescription": "First change"}
    )
    view = app(tmp_path, monkeypatch)
    next(
        c
        for c in view.checkbox
        if c.label == "Confirm release of this stale synthetic hold"
    ).check().run()
    assert not next(
        b for b in view.button if b.label == "Release stale synthetic hold"
    ).disabled
    requests.update(
        job.request_id, job.revision, {**job.fields, "jobDescription": "Second change"}
    )
    next(
        b for b in view.button if b.label == "Release stale synthetic hold"
    ).click().run()
    assert not view.exception
    assert ledger.list_reservations()[0]["state"] == "provisional"
    assert next(
        b for b in view.button if b.label == "Release stale synthetic hold"
    ).disabled


def test_corrupt_job_never_offers_release(tmp_path, monkeypatch):
    data = setup(tmp_path)
    if data is None:
        return
    _, requests, job, ledger, _ = data
    with requests._connect() as connection:
        connection.execute(
            "UPDATE intake_revisions SET fields='{}' WHERE request_id=?",
            (job.request_id,),
        )
    before = (requests.path.read_bytes(), ledger._backend.path.read_bytes())
    view = app(tmp_path, monkeypatch)
    assert not view.exception
    assert not any(b.label == "Release stale synthetic hold" for b in view.button)
    assert any(
        "Hold review or release was not confirmed" in item.value for item in view.error
    )
    assert (requests.path.read_bytes(), ledger._backend.path.read_bytes()) == before
