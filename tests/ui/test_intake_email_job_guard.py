"""Linux synthetic app journey: prepare canonical job and invalidate on answer."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from edn.operations.intake import IntakeStore
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores


def test_composed_app_prepares_job_and_guards_subsequent_answer(tmp_path, monkeypatch):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    drafts.ingest(source)
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    key = source.identity_key
    app.button(key=key + "-materialise").click().run()
    assert not app.exception
    (job,) = requests.list_requests()
    assert job.source_type == "synthetic_email" and job.state == "draft"
    requests.approve(job.request_id, 1)
    app.selectbox(key=key + "-field").select("siteLocation")
    app.text_input(key=key + "-answer").input("Corrected mobile depot")
    app.button(key=key + "-save").click().run()
    assert not app.exception
    changed = IntakeStore(requests.path).get(job.request_id)
    assert changed.state == "draft" and changed.source_pending
    assert (
        requests.source_snapshot(job.request_id)["siteLocation"]
        == "Corrected mobile depot"
    )
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert any(
        "Corrected mobile depot (operator confirmed)" in item.value
        for item in reopened.text
    )
    assert drafts.get(key)["revision"] == 2
