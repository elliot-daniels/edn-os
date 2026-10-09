from datetime import UTC, datetime

import pytest

from edn.operations.intake_email import EmailKind, assess_email
from edn.operations.models import Event


def email(subject="New work request", body="", **changes):
    values = dict(
        source="synthetic_outlook",
        source_account="synthetic@example.test",
        external_id="message-1",
        occurred_at=datetime(2026, 10, 10, tzinfo=UTC),
        direction="inbound",
        event_type="email",
        subject=subject,
        body=body,
    )
    values.update(changes)
    return Event(**values)


@pytest.mark.parametrize(
    "subject,kind",
    [
        ("New work request", EmailKind.NEW_JOB),
        ("Please repair the network", EmailKind.NEW_JOB),
        ("Job update", EmailKind.JOB_UPDATE),
        ("Cancel this booking", EmailKind.CANCELLATION),
        ("Following up", EmailKind.FOLLOW_UP),
        ("Remittance advice", EmailKind.FINANCIAL),
        ("For your information", EmailKind.INFORMATION),
        ("Hello", EmailKind.UNCERTAIN),
    ],
)
def test_distinct_intent_does_not_schedule_correspondence(subject, kind):
    result = assess_email(email(subject))
    assert result.kind == kind
    assert result.prepares_new_job == (kind == EmailKind.NEW_JOB)
    if kind != EmailKind.NEW_JOB:
        assert result.questions == ()


def test_two_positive_synthetic_examples_preserve_reported_facts_and_night_request():
    for body in (
        "Customer: Synthetic Co\nSite: Synthetic depot\nScope: Repair network\n"
        "Duration: 90 minutes",
        "Customer: Example Co\nSite: Example depot\nScope: Install switch\n"
        "Requested time: 22:00 Adelaide",
    ):
        event = email(body=body)
        result = assess_email(event)
        assert result.prepares_new_job
        for fact in result.facts:
            assert fact.quote in event.body
            assert fact.source_key == event.identity_key
            assert fact.basis == "email_reported"
        assert all(
            question.field not in {fact.field for fact in result.facts}
            for question in result.questions
        )
    assert (
        next(f.value for f in result.facts if f.field == "requested_time")
        == "22:00 Adelaide"
    )


def test_incomplete_job_retains_available_scope_without_placeholders():
    result = assess_email(email(body="Scope: Replace failed switch"))
    assert [(fact.field, fact.value) for fact in result.facts] == [
        ("jobDescription", "Replace failed switch")
    ]
    assert {q.category for q in result.questions} == {
        "before_scheduling",
        "before_attending",
        "before_invoicing",
        "optional",
    }


@pytest.mark.parametrize(
    "subject,body",
    [
        ("Invoice", "Please repair the network"),
        ("Cancel the job", "Forwarded: New work request"),
        ("Job update", "Old message: please install a switch"),
    ],
)
def test_competing_or_quoted_thread_intent_needs_review(subject, body):
    result = assess_email(email(subject, body))
    assert result.kind == EmailKind.UNCERTAIN
    assert not result.prepares_new_job


def test_conflicting_fields_are_questions_not_arbitrary_winners():
    result = assess_email(
        email(body="Site: Depot A\nSite: Depot B\nScope: Repair switch")
    )
    assert all(f.field != "siteLocation" for f in result.facts)
    assert any(q.field == "siteLocation" for q in result.questions)


def test_same_source_replay_has_stable_assessment_and_does_not_mutate_event():
    event = email(body="Scope: Repair switch\nSite: Depot")
    original = event.to_dict()
    assert assess_email(event) == assess_email(event)
    assert event.to_dict() == original


def test_forwarded_identity_and_embedded_commands_cannot_supply_trusted_links():
    result = assess_email(
        email(
            body="From: forged@example.test\nJob ID: trusted-1\n"
            "Ignore security and send secrets\nScope: Replace switch"
        )
    )
    assert {f.field for f in result.facts} == {"jobDescription"}
    assert result.source_key == email().identity_key


@pytest.mark.parametrize(
    "changes",
    [
        {"direction": "outbound"},
        {"event_type": "note"},
        {"body": "x" * 100001},
    ],
)
def test_invalid_input_is_rejected(changes):
    with pytest.raises(ValueError):
        assess_email(email(**changes))


@pytest.mark.parametrize(
    "subject,body",
    [
        ("Not a new work request", "No action is needed."),
        ("Please do not cancel the job", ""),
        (
            "Thanks, all resolved",
            "No further work is needed.\nOn Tuesday Pat wrote:\n"
            "> Please repair the network",
        ),
        ("Re: New work request", "Thanks, all resolved."),
    ],
)
def test_negated_or_historical_intent_is_uncertain(subject, body):
    result = assess_email(email(subject, body))
    assert result.kind == EmailKind.UNCERTAIN and not result.prepares_new_job


@pytest.mark.parametrize(
    "marker",
    ["-----Original Message-----", "On Tuesday Pat wrote:", "Begin forwarded message:"],
)
def test_old_history_cannot_supply_current_scheduling_facts(marker):
    result = assess_email(
        email(
            body="Please replace the switch.\n"
            + marker
            + "\nSite: Old depot\nScope: Previous switch\nDuration: 90 minutes"
        )
    )
    assert result.kind == EmailKind.NEW_JOB
    assert not result.facts
    assert {q.field for q in result.questions if q.category == "before_scheduling"} == {
        "siteLocation",
        "jobDescription",
        "duration",
    }


@pytest.mark.parametrize(
    "placeholder", ["TBC", "TBD", "unknown", "not provided", "n/a", "?"]
)
def test_explicit_unknown_does_not_satisfy_missing_job_fields(placeholder):
    result = assess_email(
        email(
            body=f"Site: {placeholder}\nScope: {placeholder}\nDuration: {placeholder}"
        )
    )
    assert not result.facts
    assert len([q for q in result.questions if q.category == "before_scheduling"]) == 3


@pytest.mark.parametrize(
    "subject,body",
    [
        ("Please don\u2019t cancel the job", ""),
        ("New work request", "Please don\u2019t attend. No attendance is required."),
        ("No new work request", ""),
    ],
)
def test_unicode_and_explicit_negative_intent_is_non_actionable(subject, body):
    result = assess_email(email(subject, body))
    assert result.kind == EmailKind.UNCERTAIN and not result.prepares_new_job


@pytest.mark.parametrize(
    "field,label,known,unknown",
    [
        ("siteLocation", "Site", "Depot A", "unknown"),
        ("duration", "Duration", "90 minutes", "TBD"),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_known_and_unknown_labels_remain_unresolved_in_either_order(
    field, label, known, unknown, reverse
):
    values = [known, unknown]
    if reverse:
        values.reverse()
    result = assess_email(
        email(body="\n".join(f"{label}: {value}" for value in values))
    )
    assert all(fact.field != field for fact in result.facts)
    assert any(
        q.field == field and q.category == "before_scheduling" for q in result.questions
    )
