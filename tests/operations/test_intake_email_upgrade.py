"""Actual old public API in a child, then current API in a fresh instance."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from edn.operations.intake_email_drafts import EmailDraftStore
from tests.operations.test_intake_email_drafts import store

CHILD = """
import importlib.util
import importlib.machinery
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from edn.operations.models import Event
def load(name, path):
    loader=importlib.machinery.SourceFileLoader(name, str(path))
    spec=importlib.util.spec_from_loader(name, loader)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    loader.exec_module(module)
    return module
fixtures=Path(sys.argv[1])
legacy_classifier=load('_legacy_email_classifier', fixtures/'classifier.py.txt')
legacy_drafts=load('_legacy_email_drafts', fixtures/'drafts.py.txt')
legacy_drafts.assess_email=legacy_classifier.assess_email
database=Path(sys.argv[2])
drafts=legacy_drafts.EmailDraftStore(database)
drafts.initialise()
event=Event(source='synthetic_outlook',source_account='synthetic@example.test',
    external_id='legacy-positive',occurred_at=datetime(2026,10,10,tzinfo=UTC),
    direction='inbound',event_type='email',subject='New work request',
    body='Scope: Repair synthetic switch\\nSite: TBC')
drafts.ingest(event)
old=drafts.answer(event.identity_key,1,'duration','60 minutes',actor='operator')
print(json.dumps(old))
"""


def test_old_head_public_api_create_answer_then_new_head_reopen(tmp_path):
    supported = store(tmp_path)
    if supported is None:
        return
    repo = Path(__file__).resolve().parents[2]
    fixtures = repo / "tests/fixtures/email-intake-legacy-v1"
    manifest = json.loads((fixtures / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        assert (
            hashlib.sha256((fixtures / entry["name"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )
    path = tmp_path / "legacy-public-api.db"
    child = subprocess.run(
        [sys.executable, "-c", CHILD, str(fixtures), str(path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(repo / "src")},
    )
    old = json.loads(child.stdout)
    assert old["revision"] == 2
    assert any(
        f["field"] == "siteLocation" and f["value"] == "TBC"
        for f in old["assessment"]["facts"]
    )
    before = path.read_bytes()
    current = EmailDraftStore(path)
    preserved = current.get(old["source_key"])
    assert preserved["assessment_stale"] and path.read_bytes() == before
    assert preserved["original"] == old["original"]
    assert preserved["answers"] == old["answers"]
    assert preserved["history"] == old["history"]
    upgraded = current.reassess_synthetic(old["source_key"], 2, actor="operator")
    assert upgraded["revision"] == 3 and not upgraded["assessment_stale"]
    assert upgraded["answers"] == old["answers"]
    assert upgraded["original"] == old["original"]
    assert any(q["field"] == "siteLocation" for q in upgraded["outstanding_questions"])
    assert current.get(old["source_key"]) == upgraded
