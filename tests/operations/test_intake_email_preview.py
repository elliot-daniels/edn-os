from datetime import datetime, timedelta

import pytest

from edn.operations.intake_email import assess_email
from edn.operations.intake_email_preview import preview_email_schedule
from edn.operations.intake_scheduling import ADELAIDE, CalendarSnapshot
from tests.operations.test_intake_email import email


def draft(body="", subject="New work request"):
    event = email(subject, body)
    assessment = assess_email(event)
    return {
        "source_key": event.identity_key,
        "answers": {},
        "assessment": {
            "kind": assessment.kind.value,
            "facts": [
                {"field": fact.field, "value": fact.value} for fact in assessment.facts
            ],
        },
    }


def snapshot(now):
    return CalendarSnapshot(
        now, now + timedelta(days=10), now, (), True, "synthetic-calendar"
    )


@pytest.mark.parametrize(
    "subject",
    ["Invoice", "FYI", "Following up", "Job update", "Cancel the job", "Hello"],
)
def test_correspondence_never_gets_a_proposal(subject):
    now = datetime(2026, 10, 12, 9, tzinfo=ADELAIDE)
    result = preview_email_schedule(
        draft("Duration: 90 minutes\nSite: Depot", subject), snapshot(now), now=now
    )
    assert result.status == "not_applicable" and result.start is None


def test_answer_resumes_schedule_and_missing_duration_is_only_an_estimate():
    now = datetime(2026, 10, 12, 9, tzinfo=ADELAIDE)
    partial = draft("Scope: Repair switch\nSite: Depot")
    assert (
        preview_email_schedule(partial, snapshot(now), now=now).status
        == "proposal_only"
    )
    partial["answers"]["duration"] = {"value": "90 minutes"}
    result = preview_email_schedule(partial, snapshot(now), now=now)
    assert result.status == "provisional_eligible"
    assert result.start == datetime(2026, 10, 12, 10, 30, tzinfo=ADELAIDE)


@pytest.mark.parametrize(
    "body",
    [
        "Requested time: 22:00 Adelaide",
        "Requested date: tomorrow",
        "Requested date: 2026-10-12\nRequested time: 25:00",
        "Requested date: 2026-10-04\nRequested time: 02:30",
        "Requested date: 2026-04-05\nRequested time: 02:30",
        "Duration: 25 hours",
    ],
)
def test_unclear_or_dst_ambiguous_requirements_are_not_silently_replaced(body):
    now = datetime(2026, 10, 2, 9, tzinfo=ADELAIDE)
    result = preview_email_schedule(draft(body), snapshot(now), now=now)
    assert result.status == "needs_clarification" and result.start is None


def test_night_requirement_preserved_as_proposal_only():
    now = datetime(2026, 10, 12, 9, tzinfo=ADELAIDE)
    result = preview_email_schedule(
        draft(
            "Site: Depot\nDuration: 90 minutes\n"
            "Requested date: 2026-10-13\nRequested time: 22:00 Adelaide"
        ),
        snapshot(now),
        now=now,
    )
    assert result.status == "proposal_only"
    assert result.start == datetime(2026, 10, 13, 22, tzinfo=ADELAIDE)
