"""Human-fact work-capture models independent of any temporary user interface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Self
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from edn.core.security import validate_identifier

SCHEMA_VERSION = "1.0.0"
MAX_SUMMARY_CHARACTERS = 500
MAX_TECHNICAL_NOTE_CHARACTERS = 1000
MAX_EVIDENCE_REFERENCES = 20
MAX_DURATION_MINUTES = 24 * 60

_SECRET_QUERY_KEYS = frozenset(
    {"token", "access_token", "refresh_token", "password", "secret", "signature"}
)


class WorkType(StrEnum):
    SITE_WORK = "site_work"
    COMMISSIONING = "commissioning"
    TESTING = "testing"
    FAULT = "fault"
    PROJECT_DELIVERY = "project_delivery"
    REMOTE_SUPPORT = "remote_support"
    ENGINEERING = "engineering"
    OPERATIONAL = "operational"
    OTHER = "other"


class OutcomeStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    UNSUCCESSFUL = "unsuccessful"
    INFORMATION_ONLY = "information_only"


class BillingTreatment(StrEnum):
    BILLABLE = "billable"
    NON_BILLABLE = "non_billable"
    REVIEW_REQUIRED = "review_required"


class RateClass(StrEnum):
    STANDARD = "standard"
    SCHEDULED_AFTER_HOURS = "scheduled_after_hours"
    NIGHT = "night"
    OTHER = "other"


class EvidenceRequirement(StrEnum):
    NOT_REQUIRED = "not_required"
    OPTIONAL = "optional"
    REQUIRED = "required"


class EvidenceStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    NOT_SUPPLIED = "not_supplied"
    COMPLETE = "complete"
    PENDING = "pending"


class PhotoPolicy(StrEnum):
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    PROHIBITED = "prohibited"


class CaptureMethod(StrEnum):
    POWER_APPS = "power_apps"
    MICROSOFT_LISTS = "microsoft_lists"
    WEB = "web"
    API = "api"
    IMPORT = "import"
    VOICE_TRANSCRIPT = "voice_transcript"


class EvidenceKind(StrEnum):
    TEST_RESULT = "test_result"
    HANDOFF_PHOTO = "handoff_photo"
    CONFIGURATION_FILE = "configuration_file"
    COMMISSIONING_RECORD = "commissioning_record"
    TECHNICAL_ARTIFACT = "technical_artifact"
    OTHER = "other"


class TechnicalValue(StrEnum):
    NONE = "none"
    CANDIDATE = "candidate"


def _clean_text(value: str, field_name: str, *, maximum: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field_name} must not be blank")
    if len(cleaned) > maximum:
        raise ValueError(f"{field_name} exceeds {maximum} characters")
    return cleaned


def _validate_reference_uri(value: str, field_name: str) -> str:
    if not value.strip() or any(character in value for character in "\r\n"):
        raise ValueError(f"{field_name} is not a valid reference URI")
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "urn"}:
        raise ValueError(f"{field_name} must use https or urn")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain credentials")
    query_keys = {
        key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    }
    if query_keys & _SECRET_QUERY_KEYS:
        raise ValueError(f"{field_name} must not contain secret query parameters")
    return value


def _optional_text(
    value: str | None, field_name: str, *, maximum: int
) -> str | None:
    return None if value is None else _clean_text(value, field_name, maximum=maximum)


@dataclass(frozen=True, slots=True)
class EntityRef:
    stable_id: str
    display_name: str
    source_uri: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.stable_id, "stable_id")
        object.__setattr__(
            self,
            "display_name",
            _clean_text(self.display_name, "display_name", maximum=200),
        )
        if self.source_uri is not None:
            _validate_reference_uri(self.source_uri, "source_uri")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "stable_id": self.stable_id,
            "display_name": self.display_name,
            "source_uri": self.source_uri,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["stable_id"]),
            str(value["display_name"]),
            _optional_str(value.get("source_uri")),
        )


@dataclass(frozen=True, slots=True)
class ActorRef:
    principal_id: str
    display_name: str
    email: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.principal_id, "principal_id")
        object.__setattr__(
            self,
            "display_name",
            _clean_text(self.display_name, "display_name", maximum=200),
        )
        if self.email is not None and (
            "@" not in self.email
            or any(character in self.email for character in "\r\n")
        ):
            raise ValueError("email is not valid")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "principal_id": self.principal_id,
            "display_name": self.display_name,
            "email": self.email,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["principal_id"]),
            str(value["display_name"]),
            _optional_str(value.get("email")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    reference_id: str
    kind: EvidenceKind
    source_uri: str
    file_name: str | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.reference_id, "reference_id")
        _validate_reference_uri(self.source_uri, "source_uri")
        if self.file_name is not None:
            object.__setattr__(
                self,
                "file_name",
                _clean_text(self.file_name, "file_name", maximum=255),
            )
        if self.content_hash is not None and not _is_sha256(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 value")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "reference_id": self.reference_id,
            "kind": self.kind.value,
            "source_uri": self.source_uri,
            "file_name": self.file_name,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["reference_id"]),
            EvidenceKind(str(value["kind"])),
            str(value["source_uri"]),
            _optional_str(value.get("file_name")),
            _optional_str(value.get("content_hash")),
        )


@dataclass(frozen=True, slots=True)
class FollowUp:
    required: bool = False
    summary: str | None = None
    due_at: datetime | None = None
    owner: ActorRef | None = None

    def __post_init__(self) -> None:
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("follow-up due_at must be timezone-aware")
        if self.required:
            if self.summary is None:
                raise ValueError("follow-up summary is required")
            object.__setattr__(
                self,
                "summary",
                _clean_text(self.summary, "follow-up summary", maximum=500),
            )
        elif any(
            value is not None for value in (self.summary, self.due_at, self.owner)
        ):
            raise ValueError("follow-up details require required=true")

    def to_dict(self) -> dict[str, object]:
        return {
            "required": self.required,
            "summary": self.summary,
            "due_at": None if self.due_at is None else self.due_at.isoformat(),
            "owner": None if self.owner is None else self.owner.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> Self:
        if value is None:
            return cls()
        owner = value.get("owner")
        return cls(
            value.get("required") is True,
            _optional_str(value.get("summary")),
            _optional_datetime(value.get("due_at")),
            None if owner is None else ActorRef.from_dict(_object(owner, "owner")),
        )


@dataclass(frozen=True, slots=True)
class ProjectDefaults:
    profile_version: str
    project: EntityRef
    client: EntityRef | None
    active: bool
    default_work_type: WorkType
    default_outcome: OutcomeStatus
    default_billing_treatment: BillingTreatment
    default_rate_class: RateClass
    default_billing_code: str | None
    task_reference_required: bool
    default_evidence_requirement: EvidenceRequirement
    evidence_by_work_type: tuple[tuple[WorkType, EvidenceRequirement], ...]
    photo_policy: PhotoPolicy
    secure_site: bool

    def __post_init__(self) -> None:
        validate_identifier(self.profile_version, "profile_version")
        object.__setattr__(self, "default_work_type", WorkType(self.default_work_type))
        object.__setattr__(
            self, "default_outcome", OutcomeStatus(self.default_outcome)
        )
        object.__setattr__(
            self,
            "default_billing_treatment",
            BillingTreatment(self.default_billing_treatment),
        )
        object.__setattr__(
            self, "default_rate_class", RateClass(self.default_rate_class)
        )
        object.__setattr__(
            self,
            "default_evidence_requirement",
            EvidenceRequirement(self.default_evidence_requirement),
        )
        object.__setattr__(self, "photo_policy", PhotoPolicy(self.photo_policy))
        if len({work_type for work_type, _ in self.evidence_by_work_type}) != len(
            self.evidence_by_work_type
        ):
            raise ValueError("evidence_by_work_type contains duplicate work types")
        if self.default_billing_code is not None:
            object.__setattr__(
                self,
                "default_billing_code",
                _clean_text(
                    self.default_billing_code,
                    "default_billing_code",
                    maximum=100,
                ),
            )

    def evidence_requirement_for(self, work_type: WorkType) -> EvidenceRequirement:
        return dict(self.evidence_by_work_type).get(
            work_type, self.default_evidence_requirement
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        evidence_value = value.get("evidence_by_work_type", {})
        if not isinstance(evidence_value, dict):
            raise ValueError("evidence_by_work_type must be an object")
        return cls(
            str(value["profile_version"]),
            EntityRef.from_dict(_object(value["project"], "project")),
            None
            if value.get("client") is None
            else EntityRef.from_dict(_object(value["client"], "client")),
            value.get("active") is True,
            WorkType(str(value["default_work_type"])),
            OutcomeStatus(str(value.get("default_outcome", "completed"))),
            BillingTreatment(str(value["default_billing_treatment"])),
            RateClass(str(value.get("default_rate_class", "standard"))),
            _optional_str(value.get("default_billing_code")),
            value.get("task_reference_required") is True,
            EvidenceRequirement(str(value["default_evidence_requirement"])),
            tuple(
                (WorkType(str(key)), EvidenceRequirement(str(requirement)))
                for key, requirement in sorted(evidence_value.items())
            ),
            PhotoPolicy(str(value["photo_policy"])),
            value.get("secure_site") is True,
        )


@dataclass(frozen=True, slots=True)
class CaptureDraft:
    submission_key: str
    project_id: str
    engineer: ActorRef
    work_date: date
    duration_minutes: int
    summary: str
    captured_at: datetime
    capture_method: CaptureMethod
    source_app_version: str
    work_started_at: datetime | None = None
    work_type: WorkType | None = None
    outcome: OutcomeStatus | None = None
    billing_treatment: BillingTreatment | None = None
    rate_class: RateClass | None = None
    billing_code: str | None = None
    task_reference: str | None = None
    follow_up: FollowUp = FollowUp()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    photo_authorization_ref: str | None = None
    technical_value: TechnicalValue = TechnicalValue.NONE
    technical_note: str | None = None
    revision: int = 1
    supersedes_capture_id: str | None = None
    correction_reason: str | None = None

    def __post_init__(self) -> None:
        try:
            normalized_submission = str(UUID(self.submission_key))
        except ValueError as exc:
            raise ValueError("submission_key must be a UUID") from exc
        object.__setattr__(self, "submission_key", normalized_submission)
        validate_identifier(self.project_id, "project_id")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.work_started_at is not None and self.work_started_at.tzinfo is None:
            raise ValueError("work_started_at must be timezone-aware")
        if self.work_started_at is not None and self.work_started_at > self.captured_at:
            raise ValueError("work_started_at must not be later than captured_at")
        if (
            self.work_started_at is not None
            and self.work_started_at.date() != self.work_date
        ):
            raise ValueError("work_started_at must fall on work_date")
        if self.work_date > self.captured_at.date():
            raise ValueError("work_date must not be later than captured_at")
        if not 1 <= self.duration_minutes <= MAX_DURATION_MINUTES:
            raise ValueError("duration_minutes must be between 1 and 1440")
        object.__setattr__(
            self,
            "summary",
            _clean_text(self.summary, "summary", maximum=MAX_SUMMARY_CHARACTERS),
        )
        object.__setattr__(
            self,
            "source_app_version",
            _clean_text(
                self.source_app_version, "source_app_version", maximum=50
            ),
        )
        if len(self.evidence_refs) > MAX_EVIDENCE_REFERENCES:
            raise ValueError("too many evidence references")
        if len({item.reference_id for item in self.evidence_refs}) != len(
            self.evidence_refs
        ):
            raise ValueError("evidence reference IDs must be unique")
        if self.photo_authorization_ref is not None:
            validate_identifier(
                self.photo_authorization_ref, "photo_authorization_ref"
            )
        object.__setattr__(
            self,
            "billing_code",
            _optional_text(self.billing_code, "billing_code", maximum=100),
        )
        object.__setattr__(
            self,
            "task_reference",
            _optional_text(self.task_reference, "task_reference", maximum=100),
        )
        object.__setattr__(
            self,
            "technical_note",
            _optional_text(
                self.technical_note,
                "technical_note",
                maximum=MAX_TECHNICAL_NOTE_CHARACTERS,
            ),
        )
        if self.technical_value is TechnicalValue.CANDIDATE and not self.technical_note:
            object.__setattr__(self, "technical_note", self.summary)
        if self.technical_value is TechnicalValue.NONE and self.technical_note:
            raise ValueError("technical_note requires technical_value=candidate")
        if self.revision < 1:
            raise ValueError("revision must be positive")
        if self.revision == 1 and any(
            value is not None
            for value in (self.supersedes_capture_id, self.correction_reason)
        ):
            raise ValueError("original captures cannot supersede another capture")
        if self.revision > 1:
            if self.supersedes_capture_id is None or self.correction_reason is None:
                raise ValueError(
                    "corrections require supersedes_capture_id and correction_reason"
                )
            validate_identifier(self.supersedes_capture_id, "supersedes_capture_id")
            object.__setattr__(
                self,
                "correction_reason",
                _clean_text(
                    self.correction_reason, "correction_reason", maximum=500
                ),
            )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        evidence = value.get("evidence_refs", [])
        if not isinstance(evidence, list):
            raise ValueError("evidence_refs must be a list")
        return cls(
            submission_key=str(value["submission_key"]),
            project_id=str(value["project_id"]),
            engineer=ActorRef.from_dict(_object(value["engineer"], "engineer")),
            work_date=date.fromisoformat(str(value["work_date"])),
            duration_minutes=int(value["duration_minutes"]),
            summary=str(value["summary"]),
            captured_at=_required_datetime(value["captured_at"], "captured_at"),
            capture_method=CaptureMethod(str(value["capture_method"])),
            source_app_version=str(value["source_app_version"]),
            work_started_at=_optional_datetime(value.get("work_started_at")),
            work_type=_optional_enum(WorkType, value.get("work_type")),
            outcome=_optional_enum(OutcomeStatus, value.get("outcome")),
            billing_treatment=_optional_enum(
                BillingTreatment, value.get("billing_treatment")
            ),
            rate_class=_optional_enum(RateClass, value.get("rate_class")),
            billing_code=_optional_str(value.get("billing_code")),
            task_reference=_optional_str(value.get("task_reference")),
            follow_up=FollowUp.from_dict(
                None
                if value.get("follow_up") is None
                else _object(value["follow_up"], "follow_up")
            ),
            evidence_refs=tuple(
                EvidenceRef.from_dict(_object(item, "evidence reference"))
                for item in evidence
            ),
            photo_authorization_ref=_optional_str(
                value.get("photo_authorization_ref")
            ),
            technical_value=TechnicalValue(
                str(value.get("technical_value", "none"))
            ),
            technical_note=_optional_str(value.get("technical_note")),
            revision=int(value.get("revision", 1)),
            supersedes_capture_id=_optional_str(
                value.get("supersedes_capture_id")
            ),
            correction_reason=_optional_str(value.get("correction_reason")),
        )


@dataclass(frozen=True, slots=True)
class WorkCapture:
    capture_id: str
    submission_key: str
    schema_version: str
    project: EntityRef
    client: EntityRef | None
    engineer: ActorRef
    work_date: date
    work_started_at: datetime | None
    duration_minutes: int
    work_type: WorkType
    summary: str
    outcome: OutcomeStatus
    billing_treatment: BillingTreatment
    rate_class: RateClass
    billing_code: str | None
    task_reference: str | None
    follow_up: FollowUp
    evidence_requirement: EvidenceRequirement
    evidence_status: EvidenceStatus
    evidence_refs: tuple[EvidenceRef, ...]
    technical_value: TechnicalValue
    technical_note: str | None
    secure_site_applied: bool
    photo_policy_applied: PhotoPolicy
    photo_authorization_ref: str | None
    capture_method: CaptureMethod
    source_app_version: str
    captured_at: datetime
    project_profile_version: str
    fact_origin: str
    defaulted_fields: tuple[str, ...]
    revision: int
    supersedes_capture_id: str | None
    correction_reason: str | None
    payload_hash: str
    ai_inferences: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.capture_id, "capture_id")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported work-capture schema version")
        if self.fact_origin != "human_confirmed":
            raise ValueError("canonical capture facts must be human_confirmed")
        if self.ai_inferences:
            raise ValueError("AI inferences must not be stored in canonical facts")
        if not _is_sha256(self.payload_hash):
            raise ValueError("payload_hash must be a lowercase SHA-256 value")

    def to_dict(self) -> dict[str, object]:
        return {
            "capture_id": self.capture_id,
            "submission_key": self.submission_key,
            "schema_version": self.schema_version,
            "project": self.project.to_dict(),
            "client": None if self.client is None else self.client.to_dict(),
            "engineer": self.engineer.to_dict(),
            "work_date": self.work_date.isoformat(),
            "work_started_at": None
            if self.work_started_at is None
            else self.work_started_at.isoformat(),
            "duration_minutes": self.duration_minutes,
            "work_type": self.work_type.value,
            "summary": self.summary,
            "outcome": self.outcome.value,
            "billing_treatment": self.billing_treatment.value,
            "rate_class": self.rate_class.value,
            "billing_code": self.billing_code,
            "task_reference": self.task_reference,
            "follow_up": self.follow_up.to_dict(),
            "evidence_requirement": self.evidence_requirement.value,
            "evidence_status": self.evidence_status.value,
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "technical_value": self.technical_value.value,
            "technical_note": self.technical_note,
            "secure_site_applied": self.secure_site_applied,
            "photo_policy_applied": self.photo_policy_applied.value,
            "photo_authorization_ref": self.photo_authorization_ref,
            "capture_method": self.capture_method.value,
            "source_app_version": self.source_app_version,
            "captured_at": self.captured_at.isoformat(),
            "project_profile_version": self.project_profile_version,
            "fact_origin": self.fact_origin,
            "defaulted_fields": list(self.defaulted_fields),
            "revision": self.revision,
            "supersedes_capture_id": self.supersedes_capture_id,
            "correction_reason": self.correction_reason,
            "payload_hash": self.payload_hash,
            "ai_inferences": [],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )


def _required_datetime(value: object, field_name: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _required_datetime(value, "datetime")


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _optional_enum(enum_type: type[StrEnum], value: object) -> Any:
    return None if value is None else enum_type(str(value))


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
