"""Synthetic target matching; replay provenance and unsafe matches fail closed."""

from dataclasses import replace
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, IntakeRequest, _digest
from edn.operations.intake_email import EmailKind, assess_email
from edn.operations.intake_email_reconciliation import match_email_job
from tests.operations.test_intake import fields
from tests.operations.test_intake_email import email


def job(**changes):
    return replace(
        IntakeRequest(
            str(uuid4()),
            3,
            fields(),
            (),
            "approved",
            "not_synced",
            "2026-10-10T00:00:00+00:00",
            "2026-10-10T00:00:00+00:00",
            3,
        ),
        **changes,
    )


def message(subject="Job update", **changes):
    return email(
        subject, "Customer: Example\nSite: Adelaide\nJob reference: PO-123", **changes
    )


def proposal(source, jobs):
    return match_email_job(source, assess_email(source), jobs, complete=True)


@pytest.mark.parametrize(
    "subject,action",
    [
        ("Job update", "update"),
        ("Cancel this booking", "cancel"),
        ("New work request", "create_or_duplicate"),
    ],
)
def test_unique_match_binds_exact_job_revision_hash_and_original_source(
    subject, action
):
    current = job()
    source = message(subject)
    result = proposal(source, [current])
    assert result.status == "matched_proposal" and result.action == action
    assert result.target_id == current.request_id and result.target_revision == 3
    assert result.target_hash == _digest(current.fields, current.attachments)
    assert result.source_key == source.identity_key
    assert proposal(replace(source, id=str(uuid4())), [current]) == result
    changed = replace(
        current, revision=4, fields=fields(jobDescription="Changed scope")
    )
    assert proposal(source, [changed]).target_hash != result.target_hash
    assert proposal(source, [changed]).target_revision == 4


@pytest.mark.parametrize(
    "subject", ["Remittance advice", "For your information", "Following up", "Hello"]
)
def test_ordinary_correspondence_never_selects_target(subject):
    result = proposal(message(subject), [job()])
    assert result.status == "not_applicable" and result.action == "none"
    assert result.target_id is None


def test_reference_alone_does_not_authorise_match_and_quote_history_is_ignored():
    source = email("Job update", "Job reference: PO-123")
    assert proposal(source, [job()]).status == "needs_information"
    assert proposal(source, [job()]).missing_fields == ("company", "siteLocation")
    forwarded = email(
        "Job update",
        "Job reference: PO-123\n--- Original Message ---\n"
        "Customer: Example\nSite: Adelaide",
    )
    assert proposal(forwarded, [job()]).status == "needs_information"


def test_multiple_matches_are_ambiguous_in_any_snapshot_order():
    one, two = job(), job()
    a, b = proposal(message(), [one, two]), proposal(message(), [two, one])
    assert a == b and a.status == "ambiguous"
    assert a.target_id is None and a.candidate_ids == tuple(
        sorted((one.request_id, two.request_id))
    )


@pytest.mark.parametrize(
    "state,pending",
    [("cancelled", False), ("rejected", False), ("draft", True), ("approved", True)],
)
def test_terminal_or_unresolved_work_requires_review(state, pending):
    result = proposal(
        message("Cancel this booking"), [job(state=state, source_pending=pending)]
    )
    assert result.status == "needs_review"


@pytest.mark.parametrize(
    "change",
    [
        dict(company="Another"),
        dict(siteLocation="Different site"),
        dict(reference="Different reference"),
    ],
)
def test_conflicting_reported_identity_never_selects_update_target(change):
    result = proposal(message(), [job(fields=fields(**change))])
    assert result.status == "unmatched" and result.target_id is None
    assert (
        proposal(message("New work request"), [job(fields=fields(**change))]).status
        == "new_candidate"
    )


def test_unsafe_reported_text_needs_clarification_not_normalised_match():
    source = email(
        "Job update", "Customer: Example\nSite: Ade\u200blaide\nJob reference: PO-123"
    )
    assert proposal(source, [job()]).status == "needs_information"
    assert proposal(source, [job()]).missing_fields == ("siteLocation",)
    assert (
        proposal(
            message(),
            [job(fields=fields(company="  EXAMPLE  ", siteLocation="ADELAIDE"))],
        ).status
        == "matched_proposal"
    )


def test_forged_assessment_live_source_and_malformed_snapshot_refuse():
    source = message()
    assessment = assess_email(source)
    with pytest.raises(IntakeError, match="stale"):
        match_email_job(source, replace(assessment, facts=()), [job()])
    with pytest.raises(IntakeError, match="stale"):
        match_email_job(
            source, replace(assessment, kind=EmailKind.INFORMATION), [job()]
        )
    with pytest.raises(IntakeError, match="another source"):
        match_email_job(replace(source, external_id="other"), assessment, [job()])
    with pytest.raises(IntakeError, match="synthetic"):
        proposal(replace(source, source="outlook"), [job()])
    current = job()
    with pytest.raises(IntakeError, match="malformed"):
        proposal(source, [current, replace(current, request_id="invalid")])
    with pytest.raises(IntakeError, match="malformed"):
        proposal(source, [current, current])


@pytest.mark.parametrize("complete", [False, None, 1, "yes"])
def test_unknown_or_untyped_coverage_never_selects_a_target(complete):
    source = message()
    result = match_email_job(source, assess_email(source), [job()], complete=complete)
    assert result.status == "snapshot_unknown" and result.target_id is None
    assert (
        match_email_job(source, assess_email(source), [job()]).status
        == "snapshot_unknown"
    )


def test_malformed_unmatched_row_cannot_hide_another_possible_target():
    source = message()
    one = job()
    corrupt = job(fields=fields(company="Another", phone="invalid"))
    with pytest.raises(IntakeError, match="malformed"):
        proposal(source, [one, corrupt])
    with pytest.raises(IntakeError, match="bound"):
        proposal(source, [one] * 1001)


def test_forwarded_source_identity_is_distinct_but_target_remains_same_job():
    source = message("New work request")
    forwarded = replace(source, external_id="forwarded-copy")
    current = job()
    one, two = proposal(source, [current]), proposal(forwarded, [current])
    assert one.source_key != two.source_key
    assert one.target_id == two.target_id == current.request_id
    assert one.target_hash == two.target_hash
