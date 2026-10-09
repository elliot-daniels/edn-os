import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from edn.operations.intake import IntakeError
from edn.operations.intake_email_drafts import EmailDraftStore
from edn.operations.intake_security import IntakeSecurityError
from tests.operations.test_intake_email import email


def store(tmp_path):
    result = EmailDraftStore(tmp_path / "email-drafts.db")
    if os.name != "posix":
        before = tuple(tmp_path.iterdir())
        with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
            result.initialise()
        assert tuple(tmp_path.iterdir()) == before
        return None
    tmp_path.chmod(0o700)
    result.initialise()
    return result


def test_incomplete_draft_and_answers_survive_restart_without_placeholder_or_approval(
    tmp_path,
):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email(body="Scope: Replace failed switch")
    first = drafts.ingest(event)
    assert first["state"] == "unapproved_email_draft"
    assert first["answers"] == {}
    answered = drafts.answer(
        event.identity_key, 1, "siteLocation", "Synthetic depot", actor="local-operator"
    )
    reopened = EmailDraftStore(tmp_path / "email-drafts.db").get(event.identity_key)
    assert reopened == answered
    assert reopened["original"] == first["original"]
    assert reopened["revision"] == 2
    assert all(q["field"] != "siteLocation" for q in reopened["outstanding_questions"])
    assert any(q["field"] == "duration" for q in reopened["outstanding_questions"])
    assert reopened["history"][-1]["actor"] == "local-operator"
    assert not hasattr(drafts, "approve") and not hasattr(drafts, "export")


def test_replay_preserves_answers_and_receipt_conflicts_fail_closed(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email(body="Scope: Replace switch")
    drafts.ingest(event)
    answered = drafts.answer(
        event.identity_key, 1, "duration", "90 minutes", actor="operator"
    )
    assert drafts.ingest(email(body=event.body)) == answered
    with pytest.raises(IntakeError, match="immutable"):
        drafts.ingest(email(body="Scope: Different work"))
    assert drafts.get(event.identity_key) == answered


def test_concurrent_answers_one_wins_without_lost_revision(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email()
    drafts.ingest(event)

    def answer(value):
        try:
            drafts.answer(
                event.identity_key, 1, "siteLocation", value, actor="operator"
            )
            return "saved"
        except IntakeError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(answer, ("Depot A", "Depot B")))
    assert sorted(outcomes) == ["saved", "stale"]
    assert drafts.get(event.identity_key)["revision"] == 2


def test_private_database_and_read_only_continuation(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email()
    drafts.ingest(event)
    path = tmp_path / "email-drafts.db"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_nlink == 1
    read = EmailDraftStore(path, read_only=True)
    assert read.get(event.identity_key)["revision"] == 1
    with pytest.raises(IntakeError, match="Read-only"):
        read.answer(event.identity_key, 1, "duration", "1 hour", actor="operator")


def test_symlink_database_cannot_write_outside_root(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    path = tmp_path / "email-drafts.db"
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    outside.chmod(0o600)
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises((IntakeSecurityError, OSError)):
        drafts.ingest(email())
    assert outside.read_bytes() == b"unchanged"


def test_malformed_assessment_is_isolated_and_no_financial_job_answers(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    positive = email()
    negative = email("Invoice", external_id="financial-1")
    drafts.ingest(positive)
    drafts.ingest(negative)
    with pytest.raises(IntakeError, match="Only a new-job"):
        drafts.answer(
            negative.identity_key, 1, "duration", "90 minutes", actor="operator"
        )
    with drafts._backend._connect() as connection:
        connection.execute(
            "UPDATE email_drafts SET assessment=? WHERE source_key=?",
            (json.dumps({"kind": "new_job"}), negative.identity_key),
        )
        connection.commit()
    valid, malformed = drafts.list_drafts()
    assert len(valid) == 1 and malformed == 1
    assert valid[0]["source_key"] == positive.identity_key
