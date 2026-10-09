import os

from streamlit.testing.v1 import AppTest

from edn.operations.intake_email_drafts import EmailDraftStore
from edn.ui.intake_email_pilot import synthetic_examples


def test_synthetic_email_queue_answer_replay_and_fresh_application(tmp_path):
    if os.name == "posix":
        tmp_path.chmod(0o700)
    script = (
        "from pathlib import Path\n"
        "from edn.ui.intake_email_pilot import render_email_pilot\n"
        f"render_email_pilot(Path({str(tmp_path)!r}))\n"
    )
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert not (tmp_path / "email-drafts.db").exists()
    app.button(key="email-pilot-load").click().run()
    assert not app.exception
    if os.name != "posix":
        assert app.error
        assert not (tmp_path / "email-drafts.db").exists()
        return
    drafts = EmailDraftStore(tmp_path / "email-drafts.db", read_only=True)
    records, malformed = drafts.list_drafts()
    assert len(records) == 6 and malformed == 0
    assert len([r for r in records if r["assessment"]["kind"] == "new_job"]) == 2
    assert any("No schedule proposed" in item.value for item in app.info)
    assert any("no reservation" in item.value for item in app.caption)
    second = synthetic_examples()[1]
    key = second.identity_key
    app.selectbox(key=key + "-field").select("duration")
    app.text_input(key=key + "-answer").input("90 minutes")
    app.button(key=key + "-save").click().run()
    assert not app.exception
    assert drafts.get(key)["revision"] == 2
    reopened = AppTest.from_string(script).run()
    assert not reopened.exception
    assert any(
        "90 minutes (operator confirmed)" in item.value for item in reopened.markdown
    )
    reopened.button(key="email-pilot-load").click().run()
    assert not reopened.exception
    assert drafts.get(key)["revision"] == 2
    assert len(drafts.list_drafts()[0]) == 6
