from pathlib import Path
from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_email_updates import UPDATE


@pytest.mark.parametrize(
    "kind", ["update", "cancel", "corrupt", "missing_binding", "rewired_binding"]
)
def test_mobile_preview_refuses_retained_email_after_job_action(
    tmp_path, monkeypatch, kind
):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    original = email(body=BODY)
    drafts.ingest(original)
    job = drafts.materialise(original.identity_key, 1, requests)
    monkeypatch.setenv("EDN_INTAKE_ROOT", str(tmp_path))
    monkeypatch.setenv("EDN_SYNTHETIC_EMAIL_PILOT", "1")
    script = Path(__file__).resolve().parents[2] / "src/edn/ui/work_intake_app.py"
    initial = AppTest.from_file(str(script)).run()
    assert not initial.exception
    assert any(
        "Provisional — Awaiting Confirmation" in item.value for item in initial.markdown
    )
    if kind in {"corrupt", "missing_binding", "rewired_binding"}:
        other = (
            requests.create(job.fields, submission_id=str(uuid4()))
            if kind == "rewired_binding"
            else None
        )
        with requests._connect() as connection:
            if kind == "corrupt":
                connection.execute(
                    "UPDATE intake_revisions SET fields='{}' WHERE request_id=?",
                    (job.request_id,),
                )
            elif kind == "missing_binding":
                connection.execute(
                    "DELETE FROM intake_sources WHERE request_id=?", (job.request_id,)
                )
            else:
                connection.execute(
                    "UPDATE intake_sources SET request_id=? WHERE request_id=?",
                    (other.request_id, job.request_id),
                )
        before = requests.path.read_bytes()
        reopened = AppTest.from_file(str(script)).run()
        assert not reopened.exception
        assert not any(
            "Provisional — Awaiting Confirmation" in item.value
            for item in reopened.markdown
        )
        assert any("could not be verified" in item.value for item in reopened.warning)
        assert requests.path.read_bytes() == before
        assert drafts.get(original.identity_key)["original"]["body"] == BODY
        return
    source = email(
        subject="Job update" if kind == "update" else "Cancel the job",
        body=UPDATE,
        external_id="action",
    )
    drafts.ingest(source)
    if kind == "update":
        changed = drafts.update_job(source.identity_key, 1, requests)
    else:
        changed = drafts.cancel_job(source.identity_key, 1, requests)
    reopened = AppTest.from_file(str(script)).run()
    assert not reopened.exception
    assert not any(
        "Provisional — Awaiting Confirmation" in item.value
        for item in reopened.markdown
    )
    assert any("Current job" in item.value for item in reopened.warning)
    assert requests.get(job.request_id) == changed
    assert drafts.get(original.identity_key)["original"]["body"] == BODY
