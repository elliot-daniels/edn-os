from pathlib import Path

from streamlit.testing.v1 import AppTest

from edn.operations.intake_email_drafts import EmailDraftStore
from edn.ui.intake_email_pilot import synthetic_forwarded_example
from tests.operations.test_intake_email_materialisation import stores


def test_forward_load_preparation_replay_and_reopen(tmp_path, monkeypatch):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    app.button(key="email-pilot-load-forward").click().run()
    assert not app.exception
    source = synthetic_forwarded_example()
    stored = EmailDraftStore(tmp_path / "email-drafts.db").get(source.identity_key)
    assert stored["assessment"]["kind"] == "new_job"
    app.button(key=source.identity_key + "-materialise").click().run()
    assert not app.exception
    (request,) = requests.list_requests()
    assert request.fields["reference"] == "SYNTH-FORWARD-01"
    assert request.fields["email"] == "contact@example.test"
    app.button(key="email-pilot-load-forward").click().run()
    app.button(key=source.identity_key + "-materialise").click().run()
    assert not app.exception
    assert requests.list_requests() == [request]
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert requests.get(request.request_id) == request
    assert drafts.get(source.identity_key)["original"] == stored["original"]
