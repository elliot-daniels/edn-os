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


def test_old_assessment_survives_read_replay_and_audited_synthetic_upgrade(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email(body="Site: TBC\nScope: Replace switch")
    drafts.ingest(event)
    answered = drafts.answer(
        event.identity_key, 1, "duration", "90 minutes", actor="operator"
    )
    legacy = dict(answered["assessment"])
    legacy.pop("version")
    legacy["reasons"] = ["Earlier classifier reason"]
    with drafts._backend._connect() as connection:
        connection.execute(
            "UPDATE email_drafts SET assessment=? WHERE source_key=?",
            (json.dumps(legacy), event.identity_key),
        )
        connection.commit()
    old = EmailDraftStore(tmp_path / "email-drafts.db").get(event.identity_key)
    assert old["assessment_stale"] is True
    assert (
        old["answers"] == answered["answers"]
        and old["original"] == answered["original"]
    )
    assert drafts.ingest(event) == old
    with pytest.raises(IntakeError, match="reassessment"):
        drafts.answer(event.identity_key, 2, "siteLocation", "Depot", actor="operator")
    updated = drafts.reassess_synthetic(event.identity_key, 2, actor="operator")
    assert updated["revision"] == 3 and updated["assessment_stale"] is False
    assert (
        updated["answers"] == old["answers"] and updated["original"] == old["original"]
    )
    assert updated["history"][-1]["previous_assessment"] == legacy
    assert drafts.reassess_synthetic(event.identity_key, 3, actor="operator") == updated


def test_non_synthetic_assessment_upgrade_refuses_before_modification(tmp_path):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email(source="outlook")
    current = drafts.ingest(event)
    with pytest.raises(IntakeError, match="owner authority"):
        drafts.reassess_synthetic(event.identity_key, 1, actor="operator")
    assert drafts.get(event.identity_key) == current


@pytest.mark.parametrize("value", ["TBC", "TBD", "unknown", "n/a"])
def test_unknown_operator_answer_cannot_close_a_required_question(tmp_path, value):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email()
    original = drafts.ingest(event)
    with pytest.raises(IntakeError, match="unknown"):
        drafts.answer(event.identity_key, 1, "siteLocation", value, actor="operator")
    assert drafts.get(event.identity_key) == original


@pytest.mark.parametrize("version", [1, 2, 3])
def test_previous_assessment_generations_reopen_with_source_and_answers_retained(
    tmp_path, version
):
    drafts = store(tmp_path)
    if drafts is None:
        return
    event = email(body="Scope: Repair synthetic switch\nSite: TBC")
    drafts.ingest(event)
    answered = drafts.answer(
        event.identity_key, 1, "duration", "60 minutes", actor="operator"
    )
    legacy = dict(answered["assessment"])
    legacy["reasons"] = ["Local conservative rules; no external AI processing"]
    if version == 1:
        legacy.pop("version")
        legacy["facts"].append(
            {
                "field": "siteLocation",
                "value": "TBC",
                "quote": "Site: TBC",
                "source_key": event.identity_key,
                "basis": "email_reported",
            }
        )
        legacy["questions"] = [
            q for q in legacy["questions"] if q["field"] != "siteLocation"
        ]
    else:
        legacy["version"] = version
    # Frozen logical receipt shapes from the old public API. Only derived
    # assessment JSON is replaced; source hash, answers and revisions are intact.
    with drafts._backend._connect() as connection:
        connection.execute(
            "UPDATE email_drafts SET assessment=? WHERE source_key=?",
            (json.dumps(legacy), event.identity_key),
        )
        connection.commit()
    reopened = EmailDraftStore(tmp_path / "email-drafts.db")
    old = reopened.get(event.identity_key)
    assert old["assessment_stale"] and old["revision"] == 2
    assert reopened.ingest(event) == old
    revised = reopened.reassess_synthetic(event.identity_key, 2, actor="operator")
    assert revised["revision"] == 3 and not revised["assessment_stale"]
    assert (
        revised["original"] == old["original"]
        and revised["source_hash"] == old["source_hash"]
    )
    assert revised["answers"] == old["answers"]
    assert revised["history"][:-1] == old["history"]
    assert any(q["field"] == "siteLocation" for q in revised["outstanding_questions"])
