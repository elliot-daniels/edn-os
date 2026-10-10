from pathlib import Path

from streamlit.testing.v1 import AppTest

from edn.operations.intake_email_drafts import EmailDraftStore
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores


def test_source_evidence_is_inert_and_answer_history_preserves_original(
    tmp_path, monkeypatch
):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    attack = "![remote](https://outside.example.test/pixel) <script>alert(1)</script>"
    source = email(subject="New work request " + attack, body=BODY + "\n" + attack)
    original = drafts.ingest(source)
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    key = source.identity_key
    assert not any(source.body == item.value for item in app.text)
    app.checkbox(key=key + "-evidence").check().run()
    assert not app.exception
    assert any(source.body == item.value for item in app.text)
    assert any(original["source_hash"] in item.value for item in app.text)
    assert any("Scope: Replace failed switch" in item.value for item in app.text)
    assert not any("outside.example.test" in item.value for item in app.markdown)
    app.selectbox(key=key + "-field").select("siteLocation")
    app.text_input(key=key + "-answer").input("Corrected synthetic depot")
    app.button(key=key + "-save").click().run()
    assert not app.exception
    assert any(
        "local-operator" in item.value and "Revision 2" in item.value
        for item in app.text
    )
    assert any(
        "Corrected synthetic depot" in item.value and "→" in item.value
        for item in app.text
    )
    assert any(source.body == item.value for item in app.text)
    stored = EmailDraftStore(tmp_path / "email-drafts.db").get(key)
    assert stored["original"] == original["original"]
    assert stored["source_hash"] == original["source_hash"]
    assert stored["history"][:-1] == original["history"]
    assert requests.list_requests() == ()
    reopened = AppTest.from_file(str(script)).run()
    reopened.checkbox(key=key + "-evidence").check().run()
    assert not reopened.exception
    assert any(source.body == item.value for item in reopened.text)
    assert any("Revision 2" in item.value for item in reopened.text)
    assert not any("outside.example.test" in item.value for item in reopened.markdown)
