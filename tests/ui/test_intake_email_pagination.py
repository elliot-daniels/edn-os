from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores


def test_mobile_reaches_old_draft_across_malformed_page_and_retains_answer(
    tmp_path, monkeypatch
):
    drafts, _ = stores(tmp_path)
    if drafts is None:
        return
    sources = [email(body=BODY, external_id=f"page-{index}") for index in range(26)]
    for source in sources:
        drafts.ingest(source)
    oldest = sources[0]
    with drafts._backend._connect() as connection:
        connection.execute(
            "UPDATE email_drafts SET original='{}' WHERE source_key=?",
            (sources[-1].identity_key,),
        )
    assert drafts.count_drafts() == 26
    before = drafts._backend.path.read_bytes()
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    view = AppTest.from_file(str(script)).run()
    assert not view.exception
    assert any("Email drafts 1 to 25 of 26" in item.value for item in view.caption)
    assert any("malformed email drafts isolated" in item.value for item in view.warning)
    assert not any(
        item.key == oldest.identity_key + "-field" for item in view.selectbox
    )
    view.button(key="email-pilot-older").click().run()
    assert not view.exception
    assert any("Email drafts 26 to 26 of 26" in item.value for item in view.caption)
    assert view.button(key="email-pilot-older").disabled
    assert drafts._backend.path.read_bytes() == before
    view.selectbox(key=oldest.identity_key + "-field").select("access_requirements")
    view.text_input(key=oldest.identity_key + "-answer").input(
        "Fictional access confirmed"
    )
    view.button(key=oldest.identity_key + "-save").click().run()
    assert not view.exception
    updated = drafts.get(oldest.identity_key)
    assert (
        updated["revision"] == 2
        and updated["answers"]["access_requirements"]["value"]
        == "Fictional access confirmed"
    )
    view.button(key="email-pilot-newer").click().run()
    assert not view.exception and view.button(key="email-pilot-newer").disabled
    view.button(key="email-pilot-older").click().run()
    assert not view.exception
    assert any(
        "Fictional access confirmed (operator confirmed)" in item.value
        for item in view.text
    )
    assert drafts.get(oldest.identity_key) == updated
