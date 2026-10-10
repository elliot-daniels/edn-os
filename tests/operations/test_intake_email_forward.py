"""Explicit preparation is distinct from incidental forwarded history."""

import pytest

from edn.operations.intake_email import EmailKind, assess_email
from edn.ui.intake_email_pilot import synthetic_forwarded_example
from tests.operations.test_intake_email import email


def forward(
    preamble="Please prepare the forwarded work request.",
    subject="New work request",
    content="Site: Depot\nScope: Replace switch\nDuration: 90 minutes",
):
    return email(
        subject="Fwd: New work request",
        body=f"{preamble}\n\n---------- Forwarded message ----------\n"
        f"From: forged@example.test\nSubject: {subject}\n\n{content}",
    )


def test_explicit_forward_facts_use_outer_event_provenance_and_original_quotes():
    event = synthetic_forwarded_example()
    original = event.to_dict()
    result = assess_email(event)
    assert result.kind == EmailKind.NEW_JOB
    assert {fact.field for fact in result.facts} >= {
        "company",
        "contactName",
        "email",
        "phone",
        "siteLocation",
        "jobDescription",
    }
    assert all(
        f.quote in event.body and f.source_key == event.identity_key
        for f in result.facts
    )
    assert all(f.basis == "email_reported" for f in result.facts)
    assert all(f.value != "forged@example.test" for f in result.facts)
    assert any("unverified" in reason for reason in result.reasons)
    assert event.to_dict() == original
    assert assess_email(event) == result


@pytest.mark.parametrize(
    "preamble",
    [
        "",
        "FYI",
        "Thanks",
        "Please cancel the job",
        "Please don't prepare the forwarded work request.",
        "Please prepare the forwarded work request.\nNo attendance is required.",
    ],
)
def test_incidental_or_negated_forward_does_not_create_new_job(preamble):
    result = assess_email(forward(preamble))
    assert result.kind != EmailKind.NEW_JOB
    assert not result.facts


@pytest.mark.parametrize(
    "subject",
    [
        "Remittance advice",
        "Job update",
        "Cancel the job",
        "Following up",
        "Not a new work request",
        "New work request and invoice",
    ],
)
def test_explicit_preparation_does_not_turn_correspondence_into_a_new_job(subject):
    result = assess_email(forward(subject=subject))
    assert result.kind == EmailKind.UNCERTAIN
    assert not result.prepares_new_job


@pytest.mark.parametrize(
    "suffix",
    [
        "\nOn Tuesday Pat wrote:\nSite: Old depot",
        "\nBegin forwarded message:\nScope: Other work",
        "\n> Site: Quoted depot",
    ],
)
def test_nested_or_quoted_history_does_not_supply_forwarded_facts(suffix):
    result = assess_email(
        forward(content="Site: Depot\nScope: Replace switch" + suffix)
    )
    assert result.kind == EmailKind.UNCERTAIN
    assert not result.facts


@pytest.mark.parametrize(
    "change",
    [
        ("Subject: New work request", "Subject: New work request\nSubject: Job update"),
        ("Subject: New work request\n\n", "Subject: New work request\n"),
        ("From: forged@example.test", "Job ID: trusted-1"),
        ("---------- Forwarded message ----------", "-----Original Message-----"),
    ],
)
def test_ambiguous_envelopes_are_not_prepared(change):
    event = forward()
    result = assess_email(
        email(subject=event.subject, body=event.body.replace(*change))
    )
    assert result.kind == EmailKind.UNCERTAIN
    assert not result.facts


def test_forwarded_conflicting_fields_and_explicit_night_requirements():
    result = assess_email(
        forward(
            content=(
                "Site: Depot A\nSite: Depot B\nScope: Replace switch\n"
                "Requested date: 2026-10-12\nRequested time: 22:00 Adelaide"
            )
        )
    )
    assert result.kind == EmailKind.NEW_JOB
    assert all(f.field != "siteLocation" for f in result.facts)
    assert any(q.field == "siteLocation" for q in result.questions)
    assert (
        next(f.value for f in result.facts if f.field == "requested_time")
        == "22:00 Adelaide"
    )
