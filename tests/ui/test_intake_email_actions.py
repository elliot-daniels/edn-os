from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_email_updates import UPDATE


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("matched", [False, True])
def test_mobile_synthetic_actions_preserve_source_and_replay(
    tmp_path, monkeypatch, cancel, matched
):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    original = email(body=BODY)
    drafts.ingest(original)
    job = drafts.materialise(original.identity_key, 1, requests)
    job = requests.approve(job.request_id, job.revision)
    source = email(
        subject="Cancel the job" if cancel else "Job update",
        body=UPDATE if matched else UPDATE.replace("SYNTH-123", "UNMATCHED-123"),
        external_id="mobile-action",
    )
    retained = drafts.ingest(source)
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    if cancel:
        assert app.button(key=source.identity_key + "-apply-action").disabled
        app.checkbox(key=source.identity_key + "-confirm-cancel").check().run()
    app.button(key=source.identity_key + "-apply-action").click().run()
    assert not app.exception
    changed = requests.get(job.request_id)
    if matched:
        assert changed.revision == job.revision + 1
        assert changed.state == ("cancelled" if cancel else "draft")
        assert changed.approved_revision is None
        assert any("Local job action verified" in item.value for item in app.success)
        assert any(
            "No calendar reservation was changed" in item.value for item in app.warning
        )
    else:
        assert changed == job
        assert any("Job action was not confirmed" in item.value for item in app.error)
    history = requests.audit_history(job.request_id)
    app.button(key=source.identity_key + "-apply-action").click().run()
    assert not app.exception
    assert requests.get(job.request_id) == changed
    assert requests.audit_history(job.request_id) == history
    assert drafts.get(source.identity_key) == retained
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert requests.get(job.request_id) == changed
