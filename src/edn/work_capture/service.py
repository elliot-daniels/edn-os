"""Resolve project defaults and plan retry-safe downstream work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TypeVar

from edn.work_capture.models import (
    SCHEMA_VERSION,
    BillingTreatment,
    CaptureDraft,
    EvidenceKind,
    EvidenceRequirement,
    EvidenceStatus,
    PhotoPolicy,
    ProjectDefaults,
    TechnicalValue,
    WorkCapture,
)

PROJECTION_VERSION = "1.0.0"
T = TypeVar("T")


class ProjectionDestination(StrEnum):
    PROJECT_ACTIVITY = "project_activity"
    ACTIONS = "actions"
    EVIDENCE_TEST_RESULTS = "evidence_test_results"
    PROJECT_FILES = "project_files"
    ENGINEERING_KNOWLEDGE = "engineering_knowledge"
    WEEKLY_SUMMARY = "weekly_summary"
    BILLING_PREPARATION = "billing_preparation"
    DAILY_INTELLIGENCE = "daily_intelligence"


class ProjectionMode(StrEnum):
    REFERENCE = "reference"
    CREATE_ONCE = "create_once"
    DERIVED_VIEW = "derived_view"


@dataclass(frozen=True, slots=True)
class ProjectionIntent:
    projection_id: str
    projection_version: str
    source_capture_id: str
    source_payload_hash: str
    destination: ProjectionDestination
    mode: ProjectionMode
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "projection_id": self.projection_id,
            "projection_version": self.projection_version,
            "source_capture_id": self.source_capture_id,
            "source_payload_hash": self.source_payload_hash,
            "destination": self.destination.value,
            "mode": self.mode.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class WorkCapturePlan:
    canonical_owner: str
    capture: WorkCapture
    projections: tuple[ProjectionIntent, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "canonical_owner": self.canonical_owner,
            "capture": self.capture.to_dict(),
            "projections": [item.to_dict() for item in self.projections],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        )


def compile_capture(draft: CaptureDraft, defaults: ProjectDefaults) -> WorkCapturePlan:
    """Create one canonical event and deterministic, non-executing projections."""
    if not defaults.active:
        raise ValueError("project is not active for work capture")
    if draft.project_id != defaults.project.stable_id:
        raise ValueError("draft project does not match the selected project profile")

    work_type, work_type_defaulted = _resolved(
        draft.work_type, defaults.default_work_type
    )
    outcome, outcome_defaulted = _resolved(draft.outcome, defaults.default_outcome)
    billing, billing_defaulted = _resolved(
        draft.billing_treatment, defaults.default_billing_treatment
    )
    rate_class, rate_defaulted = _resolved(
        draft.rate_class, defaults.default_rate_class
    )
    billing_code, billing_code_defaulted = _resolved(
        draft.billing_code, defaults.default_billing_code
    )
    if defaults.task_reference_required and not draft.task_reference:
        raise ValueError("task_reference is required by the project profile")
    if billing is BillingTreatment.BILLABLE and defaults.client is None:
        raise ValueError("billable work requires a client reference")

    evidence_requirement = defaults.evidence_requirement_for(work_type)
    _validate_photo_policy(draft, defaults.photo_policy)
    evidence_status = _evidence_status(
        evidence_requirement, bool(draft.evidence_refs)
    )
    defaulted_fields = tuple(
        field
        for field, defaulted in (
            ("work_type", work_type_defaulted),
            ("outcome", outcome_defaulted),
            ("billing_treatment", billing_defaulted),
            ("rate_class", rate_defaulted),
            ("billing_code", billing_code_defaulted),
            ("evidence_requirement", True),
            ("client", defaults.client is not None),
            ("secure_site_applied", True),
            ("photo_policy_applied", True),
        )
        if defaulted
    )
    capture_id = f"WC-{draft.submission_key}"
    capture = WorkCapture(
        capture_id=capture_id,
        submission_key=draft.submission_key,
        schema_version=SCHEMA_VERSION,
        project=defaults.project,
        client=defaults.client,
        engineer=draft.engineer,
        work_date=draft.work_date,
        work_started_at=draft.work_started_at,
        duration_minutes=draft.duration_minutes,
        work_type=work_type,
        summary=draft.summary,
        outcome=outcome,
        billing_treatment=billing,
        rate_class=rate_class,
        billing_code=billing_code,
        task_reference=draft.task_reference,
        follow_up=draft.follow_up,
        evidence_requirement=evidence_requirement,
        evidence_status=evidence_status,
        evidence_refs=draft.evidence_refs,
        technical_value=draft.technical_value,
        technical_note=draft.technical_note,
        secure_site_applied=defaults.secure_site,
        photo_policy_applied=defaults.photo_policy,
        photo_authorization_ref=draft.photo_authorization_ref,
        capture_method=draft.capture_method,
        source_app_version=draft.source_app_version,
        captured_at=draft.captured_at,
        project_profile_version=defaults.profile_version,
        fact_origin="human_confirmed",
        defaulted_fields=defaulted_fields,
        revision=draft.revision,
        supersedes_capture_id=draft.supersedes_capture_id,
        correction_reason=draft.correction_reason,
        payload_hash="0" * 64,
    )
    payload_hash = _payload_hash(capture)
    capture = replace(capture, payload_hash=payload_hash)
    return WorkCapturePlan("Work Log", capture, _projection_plan(capture))


def _resolved(value: T | None, default: T) -> tuple[T, bool]:
    return (default, True) if value is None else (value, False)


def _validate_photo_policy(draft: CaptureDraft, policy: PhotoPolicy) -> None:
    has_photo = any(
        item.kind is EvidenceKind.HANDOFF_PHOTO for item in draft.evidence_refs
    )
    if has_photo and policy is PhotoPolicy.PROHIBITED:
        raise PermissionError("project policy prohibits photographic evidence")
    if (
        has_photo
        and policy is PhotoPolicy.RESTRICTED
        and draft.photo_authorization_ref is None
    ):
        raise PermissionError(
            "restricted photographic evidence requires an authorization reference"
        )
    if draft.photo_authorization_ref is not None and not has_photo:
        raise ValueError("photo authorization is valid only when a photo is referenced")


def _evidence_status(
    requirement: EvidenceRequirement, has_references: bool
) -> EvidenceStatus:
    if has_references:
        return EvidenceStatus.COMPLETE
    if requirement is EvidenceRequirement.REQUIRED:
        return EvidenceStatus.PENDING
    if requirement is EvidenceRequirement.OPTIONAL:
        return EvidenceStatus.NOT_SUPPLIED
    return EvidenceStatus.NOT_REQUIRED


def _payload_hash(capture: WorkCapture) -> str:
    value = capture.to_dict()
    value.pop("payload_hash")
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _projection_plan(capture: WorkCapture) -> tuple[ProjectionIntent, ...]:
    values: list[tuple[ProjectionDestination, ProjectionMode, str]] = [
        (
            ProjectionDestination.PROJECT_ACTIVITY,
            ProjectionMode.REFERENCE,
            "Project history resolves the canonical Work Log record by project ID.",
        ),
        (
            ProjectionDestination.WEEKLY_SUMMARY,
            ProjectionMode.DERIVED_VIEW,
            "Weekly time is calculated from canonical duration and work date.",
        ),
        (
            ProjectionDestination.DAILY_INTELLIGENCE,
            ProjectionMode.DERIVED_VIEW,
            "Daily Intelligence may retrieve this source record under separate "
            "authority.",
        ),
    ]
    if capture.billing_treatment in {
        BillingTreatment.BILLABLE,
        BillingTreatment.REVIEW_REQUIRED,
    }:
        values.append(
            (
                ProjectionDestination.BILLING_PREPARATION,
                ProjectionMode.DERIVED_VIEW,
                "Invoice preparation derives time and billing classification "
                "without copying facts.",
            )
        )
    if capture.follow_up.required:
        values.append(
            (
                ProjectionDestination.ACTIONS,
                ProjectionMode.CREATE_ONCE,
                "The engineer explicitly requested a follow-up action.",
            )
        )
    if (
        capture.evidence_refs
        or capture.evidence_requirement is EvidenceRequirement.REQUIRED
    ):
        values.extend(
            (
                (
                    ProjectionDestination.EVIDENCE_TEST_RESULTS,
                    ProjectionMode.REFERENCE,
                    "Evidence status and source references remain linked to the "
                    "capture.",
                ),
                (
                    ProjectionDestination.PROJECT_FILES,
                    ProjectionMode.REFERENCE,
                    "Project files retain binary content and a backlink to the "
                    "capture.",
                ),
            )
        )
    if capture.technical_value is TechnicalValue.CANDIDATE:
        values.append(
            (
                ProjectionDestination.ENGINEERING_KNOWLEDGE,
                ProjectionMode.CREATE_ONCE,
                "Human marked the work as a reviewable knowledge candidate.",
            )
        )
    return tuple(
        ProjectionIntent(
            _projection_id(capture.capture_id, destination),
            PROJECTION_VERSION,
            capture.capture_id,
            capture.payload_hash,
            destination,
            mode,
            reason,
        )
        for destination, mode, reason in values
    )


def _projection_id(
    capture_id: str, destination: ProjectionDestination
) -> str:
    digest = hashlib.sha256(
        f"{capture_id}:{destination.value}:{PROJECTION_VERSION}".encode()
    ).hexdigest()[:24]
    return f"WCP-{digest}"
