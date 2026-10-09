import os
from pathlib import Path

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
    assert any("Unverified 60-minute" in item.value for item in app.warning)
    assert any("Service:" in item.value for item in app.markdown)
    assert any("Travel/preparation occupancy:" in item.value for item in app.markdown)
    assert any(
        "Duration is an uncertain estimate" in item.value for item in app.markdown
    )
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
        "90 minutes (operator confirmed)" in item.value for item in reopened.text
    )
    reopened.button(key="email-pilot-load").click().run()
    assert not reopened.exception
    assert drafts.get(key)["revision"] == 2
    assert len(drafts.list_drafts()[0]) == 6


def test_two_sessions_cannot_rebind_stale_input_to_newer_revision(tmp_path):
    if os.name != "posix":
        return  # Linux runtime only; platform refusal is independently asserted above.
    tmp_path.chmod(0o700)
    script = (
        "from pathlib import Path\n"
        "from edn.ui.intake_email_pilot import render_email_pilot\n"
        f"render_email_pilot(Path({str(tmp_path)!r}))\n"
    )
    first = AppTest.from_string(script).run()
    first.button(key="email-pilot-load").click().run()
    second = AppTest.from_string(script).run()
    key = synthetic_examples()[1].identity_key
    first.selectbox(key=key + "-field").select("siteLocation")
    first.text_input(key=key + "-answer").input("Stale depot input")
    second.selectbox(key=key + "-field").select("duration")
    second.text_input(key=key + "-answer").input("90 minutes")
    second.button(key=key + "-save").click().run()
    assert not second.exception
    first.button(key=key + "-save").click().run()
    assert not first.exception
    assert any("changed in another session" in item.value for item in first.warning)
    drafts = EmailDraftStore(tmp_path / "email-drafts.db", read_only=True)
    current = drafts.get(key)
    assert current["revision"] == 2
    assert "siteLocation" not in current["answers"]
    first.button(key=key + "-refresh").click().run()
    assert not first.exception
    assert first.text_input(key=key + "-answer").value == ""


def test_opt_in_composed_work_intake_app_path(tmp_path, monkeypatch):
    from tests.operations.test_intake import store

    requests = store(tmp_path)
    if requests is None:
        return
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    source = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(source)).run()
    assert not app.exception
    app.button(key="email-pilot-load").click().run()
    assert not app.exception
    assert any(item.value == "Intake queue" for item in app.subheader)
    assert len(EmailDraftStore(tmp_path / "email-drafts.db").list_drafts()[0]) == 6


def test_source_markdown_is_plain_text_not_remote_resource_markup(tmp_path):
    from tests.operations.test_intake_email import email
    from tests.operations.test_intake_email_drafts import store

    drafts = store(tmp_path)
    if drafts is None:
        return
    marker = "![tracking](https://example.invalid/pixel)"
    event = email("New work request " + marker, "Scope: " + marker)
    drafts.ingest(event)
    script = (
        "from pathlib import Path\n"
        "from edn.ui.intake_email_pilot import render_email_pilot\n"
        f"render_email_pilot(Path({str(tmp_path)!r}))\n"
    )
    app = AppTest.from_string(script).run()
    assert not app.exception
    assert any(marker in element.value for element in app.text)
    assert all(marker not in element.value for element in app.markdown)
    assert all(marker not in element.label for element in app.expander)
