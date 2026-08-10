"""Immutable persistent job, retry, progress, result, and audit contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from edn.connectors import ConnectorPlan, VerificationStatus
from edn.core import Classification, PrincipalContext, Purpose, SecurityDomain
from edn.core.security import SCHEMA_VERSION, validate_identifier


class JobStatus(StrEnum):
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"


class JobType(StrEnum):
    DISCOVERY = "discovery"
    INGESTION = "ingestion"
    SYNC = "sync"
    SEARCH = "search"
    ACTION = "action"
    VERIFICATION = "verification"
    OTHER = "other"


TERMINAL_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.INDETERMINATE,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    retryable_error_codes: frozenset[str] = frozenset({"transient_failure"})

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must not be negative")
        for code in self.retryable_error_codes:
            validate_identifier(code, "retryable_error_codes")

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be at least one")
        return float(self.base_delay_seconds * (2 ** (attempt - 1)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "base_delay_seconds": self.base_delay_seconds,
            "retryable_error_codes": sorted(self.retryable_error_codes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            int(value["max_attempts"]),
            float(value["base_delay_seconds"]),
            _string_set(value.get("retryable_error_codes"), "retryable_error_codes"),
        )


@dataclass(frozen=True, slots=True)
class JobProgress:
    phase: str
    processed_items: int = 0
    total_items: int | None = None
    checkpoint_count: int = 0

    def __post_init__(self) -> None:
        validate_identifier(self.phase, "phase")
        if self.processed_items < 0 or self.checkpoint_count < 0:
            raise ValueError("progress counts must not be negative")
        if self.total_items is not None and self.total_items < self.processed_items:
            raise ValueError("total_items must not be less than processed_items")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "processed_items": self.processed_items,
            "total_items": self.total_items,
            "checkpoint_count": self.checkpoint_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["phase"]),
            int(value["processed_items"]),
            _optional_int(value.get("total_items")),
            int(value["checkpoint_count"]),
        )


@dataclass(frozen=True, slots=True)
class JobResultRef:
    result_type: str
    references: tuple[str, ...] = ()
    item_count: int = 0
    summary: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.result_type, "result_type")
        for reference in self.references:
            _validate_safe_text(reference, "references")
        if self.item_count < 0:
            raise ValueError("item_count must not be negative")
        if self.summary is not None and (
            not self.summary.strip() or len(self.summary) > 512
        ):
            raise ValueError("summary must be bounded and nonblank")

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_type": self.result_type,
            "references": list(self.references),
            "item_count": self.item_count,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["result_type"]),
            _string_tuple(value.get("references"), "references"),
            int(value["item_count"]),
            _optional_str(value.get("summary")),
        )


@dataclass(frozen=True, slots=True)
class JobError:
    code: str
    explanation: str
    retryable: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.code, "code")
        _validate_safe_text(self.explanation, "explanation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "explanation": self.explanation,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["code"]),
            str(value["explanation"]),
            _strict_bool(value.get("retryable")),
        )


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    approval_ref: str
    plan_id: str
    plan_hash: str
    scope: tuple[str, ...]
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.approval_ref, "approval_ref")
        validate_identifier(self.plan_id, "plan_id")
        if not _is_sha256(self.plan_hash):
            raise ValueError("plan_hash must be a lowercase SHA-256 value")
        for item in self.scope:
            validate_identifier(item, "scope")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")

    def matches(self, plan: ConnectorPlan, *, now: datetime) -> bool:
        return (
            self.plan_id == plan.plan_id
            and self.plan_hash == plan.plan_hash
            and self.scope == plan.scope
            and (self.expires_at is None or now < self.expires_at)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_ref": self.approval_ref,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
            "scope": list(self.scope),
            "expires_at": _format_datetime(self.expires_at),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        return cls(
            str(value["approval_ref"]),
            str(value["plan_id"]),
            str(value["plan_hash"]),
            _string_tuple(value.get("scope"), "scope"),
            _parse_datetime(value.get("expires_at")),
        )


@dataclass(frozen=True, slots=True)
class Job:
    job_id: str
    job_type: JobType
    connector_id: str
    connector_version: str
    configuration_hash: str
    capability_id: str
    operation: str
    principal: PrincipalContext
    purpose: Purpose
    security_domain: SecurityDomain
    classification: Classification
    resource_scope: tuple[str, ...]
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    status: JobStatus
    retry_policy: RetryPolicy
    progress: JobProgress
    plan: ConnectorPlan | None = None
    approval: ApprovalBinding | None = None
    authority_ref: str | None = None
    attempt_count: int = 0
    checkpoint_id: str | None = None
    result: JobResultRef | None = None
    verification_status: VerificationStatus | None = None
    error: JobError | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    next_retry_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "job_id",
            "connector_id",
            "connector_version",
            "capability_id",
            "operation",
            "correlation_id",
        ):
            validate_identifier(getattr(self, name), name)
        if not _is_sha256(self.configuration_hash):
            raise ValueError("configuration_hash must be a lowercase SHA-256 value")
        for item in self.resource_scope:
            validate_identifier(item, "resource_scope")
        for value in (
            self.created_at,
            self.updated_at,
            self.started_at,
            self.completed_at,
            self.next_retry_at,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("job timestamps must be timezone-aware")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must not be negative")
        for name in ("authority_ref", "checkpoint_id"):
            value = getattr(self, name)
            if value is not None:
                validate_identifier(value, name)
        if self.status is JobStatus.AWAITING_APPROVAL and self.plan is None:
            raise ValueError("approval-awaiting job requires a plan")
        if self.status in {
            JobStatus.COMPLETED,
            JobStatus.COMPLETED_WITH_WARNINGS,
        } and (self.completed_at is None or self.result is None):
            raise ValueError("completed job requires result and completion time")
        if self.status is JobStatus.RETRY_WAIT and self.next_retry_at is None:
            raise ValueError("retry_wait requires next_retry_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "connector_id": self.connector_id,
            "connector_version": self.connector_version,
            "configuration_hash": self.configuration_hash,
            "capability_id": self.capability_id,
            "operation": self.operation,
            "principal": self.principal.to_dict(),
            "purpose": self.purpose.to_dict(),
            "security_domain": self.security_domain.to_dict(),
            "classification": self.classification.to_dict(),
            "resource_scope": list(self.resource_scope),
            "correlation_id": self.correlation_id,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
            "status": self.status.value,
            "retry_policy": self.retry_policy.to_dict(),
            "progress": self.progress.to_dict(),
            "plan": None if self.plan is None else self.plan.to_dict(),
            "approval": None if self.approval is None else self.approval.to_dict(),
            "authority_ref": self.authority_ref,
            "attempt_count": self.attempt_count,
            "checkpoint_id": self.checkpoint_id,
            "result": None if self.result is None else self.result.to_dict(),
            "verification_status": None
            if self.verification_status is None
            else self.verification_status.value,
            "error": None if self.error is None else self.error.to_dict(),
            "started_at": _format_datetime(self.started_at),
            "completed_at": _format_datetime(self.completed_at),
            "next_retry_at": _format_datetime(self.next_retry_at),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported or missing schema_version")
        return cls(
            job_id=str(value["job_id"]),
            job_type=JobType(value["job_type"]),
            connector_id=str(value["connector_id"]),
            connector_version=str(value["connector_version"]),
            configuration_hash=str(value["configuration_hash"]),
            capability_id=str(value["capability_id"]),
            operation=str(value["operation"]),
            principal=PrincipalContext.from_dict(_dict(value["principal"])),
            purpose=Purpose.from_dict(_dict(value["purpose"])),
            security_domain=SecurityDomain.from_dict(_dict(value["security_domain"])),
            classification=Classification.from_dict(_dict(value["classification"])),
            resource_scope=_string_tuple(value.get("resource_scope"), "resource_scope"),
            correlation_id=str(value["correlation_id"]),
            created_at=_required_datetime(value.get("created_at"), "created_at"),
            updated_at=_required_datetime(value.get("updated_at"), "updated_at"),
            status=JobStatus(value["status"]),
            retry_policy=RetryPolicy.from_dict(_dict(value["retry_policy"])),
            progress=JobProgress.from_dict(_dict(value["progress"])),
            plan=_optional_model(value.get("plan"), ConnectorPlan.from_dict),
            approval=_optional_model(value.get("approval"), ApprovalBinding.from_dict),
            authority_ref=_optional_str(value.get("authority_ref")),
            attempt_count=int(value.get("attempt_count", 0)),
            checkpoint_id=_optional_str(value.get("checkpoint_id")),
            result=_optional_model(value.get("result"), JobResultRef.from_dict),
            verification_status=_optional_enum(
                value.get("verification_status"), VerificationStatus
            ),
            error=_optional_model(value.get("error"), JobError.from_dict),
            started_at=_parse_datetime(value.get("started_at")),
            completed_at=_parse_datetime(value.get("completed_at")),
            next_retry_at=_parse_datetime(value.get("next_retry_at")),
        )


@dataclass(frozen=True, slots=True)
class JobAttempt:
    job_id: str
    attempt_number: int
    worker_id: str
    started_at: datetime
    completed_at: datetime | None = None
    outcome: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    job_id: str
    event_type: str
    timestamp: datetime
    correlation_id: str
    actor_id: str | None = None
    previous_status: JobStatus | None = None
    new_status: JobStatus | None = None
    reason_code: str | None = None
    metadata: tuple[tuple[str, str | int | bool | None], ...] = ()

    def __post_init__(self) -> None:
        for name in ("event_id", "job_id", "event_type", "correlation_id"):
            validate_identifier(getattr(self, name), name)
        if self.timestamp.tzinfo is None:
            raise ValueError("audit timestamp must be timezone-aware")
        for name in ("actor_id", "reason_code"):
            value = getattr(self, name)
            if value is not None:
                validate_identifier(value, name)
        for key, value in self.metadata:
            validate_identifier(key, "metadata key")
            if any(
                fragment in key.casefold() for fragment in _PROHIBITED_METADATA_KEYS
            ):
                raise ValueError("audit metadata key may contain sensitive content")
            if isinstance(value, str):
                _validate_safe_text(value, "audit metadata value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": self.event_id,
            "job_id": self.job_id,
            "event_type": self.event_type,
            "timestamp": _format_datetime(self.timestamp),
            "correlation_id": self.correlation_id,
            "actor_id": self.actor_id,
            "previous_status": None
            if self.previous_status is None
            else self.previous_status.value,
            "new_status": None if self.new_status is None else self.new_status.value,
            "reason_code": self.reason_code,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        metadata = value.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("audit metadata must be an object")
        return cls(
            str(value["event_id"]),
            str(value["job_id"]),
            str(value["event_type"]),
            _required_datetime(value.get("timestamp"), "timestamp"),
            str(value["correlation_id"]),
            _optional_str(value.get("actor_id")),
            _optional_enum(value.get("previous_status"), JobStatus),
            _optional_enum(value.get("new_status"), JobStatus),
            _optional_str(value.get("reason_code")),
            tuple(sorted(metadata.items())),
        )


_PROHIBITED_METADATA_KEYS = (
    "body",
    "content",
    "password",
    "secret",
    "token",
    "credential",
    "payload",
)


def _validate_safe_text(value: str, field_name: str) -> None:
    if not value.strip() or any(char in value for char in "\r\n") or len(value) > 512:
        raise ValueError(f"{field_name} must be bounded, nonblank, and single-line")


def _dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("nested value must be an object")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return tuple(value)


def _string_set(value: object, field_name: str) -> frozenset[str]:
    return frozenset(_string_tuple(value, field_name))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer")
    return value


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("value must be a boolean")
    return value


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _required_datetime(value: object, field_name: str) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(f"{field_name} is required")
    return parsed


def _optional_model(value: object, loader: Any) -> Any:
    return None if value is None else loader(_dict(value))


def _optional_enum(value: object, enum_type: Any) -> Any:
    return None if value is None else enum_type(value)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)
