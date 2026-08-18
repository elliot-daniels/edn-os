from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from edn.work_capture import (
    ActorRef,
    BillingTreatment,
    CaptureDraft,
    CaptureMethod,
    EntityRef,
    EvidenceKind,
    EvidenceRef,
    EvidenceRequirement,
    EvidenceStatus,
    FollowUp,
    OutcomeStatus,
    PhotoPolicy,
    ProjectDefaults,
    ProjectionDestination,
    ProjectionMode,
    RateClass,
    TechnicalValue,
    WorkType,
    compile_capture,
)
from edn.work_capture.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "400g-test-pending.json"
CAPTURED = datetime.fromisoformat("2026-08-18T22:33:00+09:30")


def _defaults(*, photo_policy: PhotoPolicy = PhotoPolicy.PROHIBITED):
    return ProjectDefaults(
        "PROFILE-ONE",
        EntityRef("PRJ-ONE", "Synthetic Project"),
        EntityRef("CLI-ONE", "Synthetic Client"),
        True,
        WorkType.TESTING,
        OutcomeStatus.COMPLETED,
        BillingTreatment.BILLABLE,
        RateClass.STANDARD,
        "BILL-ONE",
        False,
        EvidenceRequirement.OPTIONAL,
        ((WorkType.TESTING, EvidenceRequirement.REQUIRED),),
        photo_policy,
        True,
    )


def _draft(**changes: object) -> CaptureDraft:
    value = CaptureDraft(
        "93e2088b-197c-43d5-a822-6c9b17e4aff7",
        "PRJ-ONE",
        ActorRef("engineer-one", "Synthetic Engineer"),
        date(2026, 8, 18),
        90,
        "400G test completed after correcting the remote FEC configuration.",
        CAPTURED,
        CaptureMethod.POWER_APPS,
        "uwc-test-v1",
    )
    return replace(value, **changes)


def test_400g_capture_applies_defaults_and_retains_pending_evidence() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    plan = compile_capture(
        CaptureDraft.from_dict(value["draft"]),
        ProjectDefaults.from_dict(value["project_defaults"]),
    )

    capture = plan.capture
    assert plan.canonical_owner == "Work Log"
    assert capture.capture_id == "WC-b06f89a8-f836-42d6-87df-4af8c245dbad"
    assert capture.client is not None
    assert capture.client.stable_id == "CLI-SYNTH-001"
    assert capture.work_type is WorkType.TESTING
    assert capture.evidence_requirement is EvidenceRequirement.REQUIRED
    assert capture.evidence_status is EvidenceStatus.PENDING
    assert capture.photo_policy_applied is PhotoPolicy.PROHIBITED
    assert capture.fact_origin == "human_confirmed"
    assert capture.ai_inferences == ()
    assert {
        "work_type",
        "outcome",
        "billing_treatment",
        "rate_class",
        "billing_code",
        "evidence_requirement",
        "client",
    } <= set(capture.defaulted_fields)

    destinations = {item.destination: item for item in plan.projections}
    assert destinations[ProjectionDestination.ENGINEERING_KNOWLEDGE].mode is (
        ProjectionMode.CREATE_ONCE
    )
    assert ProjectionDestination.EVIDENCE_TEST_RESULTS in destinations
    assert ProjectionDestination.BILLING_PREPARATION in destinations
    assert ProjectionDestination.ACTIONS not in destinations


def test_viavi_reference_completes_evidence_without_storing_binary() -> None:
    result = EvidenceRef(
        "VIAVI-RESULT-001",
        EvidenceKind.TEST_RESULT,
        "https://example.sharepoint.com/sites/edn/results/viavi-001.pdf",
        "viavi-001.pdf",
        "a" * 64,
    )
    plan = compile_capture(_draft(evidence_refs=(result,)), _defaults())

    assert plan.capture.evidence_status is EvidenceStatus.COMPLETE
    serialized = plan.capture.to_json()
    assert "viavi-001.pdf" in serialized
    assert "binary" not in serialized
    assert "content" not in plan.capture.evidence_refs[0].to_dict()


def test_prohibited_photo_fails_before_a_plan_is_created() -> None:
    photo = EvidenceRef(
        "PHOTO-ONE",
        EvidenceKind.HANDOFF_PHOTO,
        "https://example.sharepoint.com/sites/edn/project-files/photo.jpg",
    )

    with pytest.raises(PermissionError, match="prohibits photographic"):
        compile_capture(_draft(evidence_refs=(photo,)), _defaults())


def test_restricted_photo_requires_explicit_authorization_reference() -> None:
    photo = EvidenceRef(
        "PHOTO-ONE",
        EvidenceKind.HANDOFF_PHOTO,
        "https://example.sharepoint.com/sites/edn/project-files/photo.jpg",
    )
    defaults = _defaults(photo_policy=PhotoPolicy.RESTRICTED)

    with pytest.raises(PermissionError, match="authorization reference"):
        compile_capture(_draft(evidence_refs=(photo,)), defaults)

    plan = compile_capture(
        _draft(
            evidence_refs=(photo,),
            photo_authorization_ref="PHOTO-AUTH-001",
        ),
        defaults,
    )
    assert plan.capture.photo_authorization_ref == "PHOTO-AUTH-001"


def test_explicit_follow_up_generates_one_deterministic_action_intent() -> None:
    follow_up = FollowUp(
        True,
        "Confirm the remote-end configuration baseline.",
        datetime.fromisoformat("2026-08-20T09:00:00+09:30"),
    )
    first = compile_capture(_draft(follow_up=follow_up), _defaults())
    second = compile_capture(_draft(follow_up=follow_up), _defaults())
    actions = [
        item
        for item in first.projections
        if item.destination is ProjectionDestination.ACTIONS
    ]

    assert len(actions) == 1
    assert actions[0].mode is ProjectionMode.CREATE_ONCE
    assert first.capture.payload_hash == second.capture.payload_hash
    assert first.projections == second.projections


def test_same_submission_with_changed_facts_has_same_id_but_conflicting_hash() -> None:
    first = compile_capture(_draft(), _defaults())
    changed = compile_capture(_draft(duration_minutes=120), _defaults())

    assert first.capture.capture_id == changed.capture.capture_id
    assert first.capture.payload_hash != changed.capture.payload_hash


def test_required_task_reference_is_conditional() -> None:
    defaults = replace(_defaults(), task_reference_required=True)

    with pytest.raises(ValueError, match="task_reference"):
        compile_capture(_draft(), defaults)

    plan = compile_capture(_draft(task_reference="TASK-400G-01"), defaults)
    assert plan.capture.task_reference == "TASK-400G-01"


def test_non_billable_valuable_work_still_becomes_knowledge_candidate() -> None:
    defaults = replace(
        _defaults(),
        client=None,
        default_work_type=WorkType.OPERATIONAL,
        default_billing_treatment=BillingTreatment.NON_BILLABLE,
        default_evidence_requirement=EvidenceRequirement.NOT_REQUIRED,
        evidence_by_work_type=(),
        photo_policy=PhotoPolicy.ALLOWED,
        secure_site=False,
    )
    plan = compile_capture(
        _draft(
            work_type=WorkType.OPERATIONAL,
            technical_value=TechnicalValue.CANDIDATE,
            technical_note="Reusable recovery sequence validated.",
        ),
        defaults,
    )
    destinations = {item.destination for item in plan.projections}

    assert plan.capture.client is None
    assert plan.capture.billing_treatment is BillingTreatment.NON_BILLABLE
    assert ProjectionDestination.BILLING_PREPARATION not in destinations
    assert ProjectionDestination.ENGINEERING_KNOWLEDGE in destinations


def test_billable_work_requires_a_client_reference() -> None:
    defaults = replace(_defaults(), client=None)

    with pytest.raises(ValueError, match="requires a client"):
        compile_capture(_draft(), defaults)


def test_start_time_must_match_work_date_and_precede_capture() -> None:
    with pytest.raises(ValueError, match="later than captured"):
        _draft(
            work_started_at=datetime.fromisoformat(
                "2026-08-18T23:00:00+09:30"
            )
        )

    with pytest.raises(ValueError, match="fall on work_date"):
        _draft(
            work_started_at=datetime.fromisoformat(
                "2026-08-17T23:00:00+09:30"
            )
        )


def test_evidence_uri_rejects_secret_query_parameters() -> None:
    with pytest.raises(ValueError, match="secret query"):
        EvidenceRef(
            "RESULT-ONE",
            EvidenceKind.TEST_RESULT,
            "https://example.invalid/result?access_token=secret",
        )


def test_corrections_are_append_only() -> None:
    with pytest.raises(ValueError, match="corrections require"):
        _draft(revision=2)

    corrected = _draft(
        submission_key="a438deea-3e52-4274-b6af-a189584fba95",
        revision=2,
        supersedes_capture_id="WC-93e2088b-197c-43d5-a822-6c9b17e4aff7",
        correction_reason="Corrected duration after engineer review.",
    )
    plan = compile_capture(corrected, _defaults())
    assert plan.capture.revision == 2
    assert plan.capture.supersedes_capture_id is not None


def test_cli_renders_synthetic_plan(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(FIXTURE)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["canonical_owner"] == "Work Log"
    assert output["capture"]["summary"].startswith("400G test completed")
    assert output["capture"]["ai_inferences"] == []
