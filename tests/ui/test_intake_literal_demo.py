from pathlib import Path

from streamlit.testing.v1 import AppTest

from edn.operations.intake_email import EmailKind, assess_email
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.ui.intake_email_pilot import synthetic_literal_example
from tests.operations.test_intake_email_materialisation import stores


def test_fictional_literal_fixture_has_reported_prose_not_verified_identity():
    source = synthetic_literal_example()
    result = assess_email(source)
    assert source.source.startswith("synthetic_")
    assert result.kind == EmailKind.NEW_JOB
    facts = {fact.field: fact for fact in result.facts}
    assert facts["siteLocation"].value == "Synthetic literal depot"
    assert facts["jobDescription"].value == "replace the failed switch"
    assert all(
        fact.quote in source.body and fact.basis == "email_reported"
        for fact in result.facts
    )


def test_mobile_literal_fixture_prepare_hold_replay_and_reopen(tmp_path, monkeypatch):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    view = AppTest.from_file(str(script)).run()
    assert not view.exception
    view.button(key="email-pilot-load-literal").click().run()
    assert not view.exception
    source = synthetic_literal_example()
    original = drafts.get(source.identity_key)
    view.button(key=source.identity_key + "-materialise").click().run()
    assert not view.exception
    (job,) = requests.list_requests()
    assert job.fields["jobDescription"] == "replace the failed switch"
    assert job.fields["siteLocation"] == "Synthetic literal depot"
    assert job.state == "draft" and job.approved_revision is None
    view.button(key=source.identity_key + "-reserve").click().run()
    assert not view.exception
    ledger = SyntheticReservationStore(tmp_path / "reservations.db")
    (hold,) = ledger.list_reservations()
    assert hold["job_id"] == job.request_id and hold["state"] == "provisional"
    assert any(
        "already has a verified synthetic provisional hold" in item.value
        for item in view.info
    )
    view.button(key="email-pilot-load-literal").click().run()
    assert not view.exception
    assert requests.list_requests() == (job,)
    assert ledger.list_reservations() == (hold,)
    assert drafts.get(source.identity_key) == original
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert requests.list_requests() == (job,) and ledger.list_reservations() == (hold,)
    assert any(
        "already has a verified synthetic provisional hold" in item.value
        for item in reopened.info
    )
