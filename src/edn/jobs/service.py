"""Job lifecycle service and pure execution-time reauthorization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import uuid4

from edn.core import (
    CapabilityRegistry,
    CapabilityUseDecision,
    PermissionEvaluator,
    PermissionRequest,
    evaluate_capability_use,
)
from edn.jobs.models import ApprovalBinding, AuditEvent, Job, JobStatus
from edn.jobs.storage import JobStore


@dataclass(frozen=True, slots=True)
class ReauthorizationResult:
    usable: bool
    reason_code: str
    explanation: str
    authority: CapabilityUseDecision | None = None


def reauthorize_job(
    job: Job,
    registry: CapabilityRegistry,
    evaluator: PermissionEvaluator,
    *,
    now: datetime,
) -> ReauthorizationResult:
    if now.tzinfo is None:
        raise ValueError("reauthorization time must be timezone-aware")
    capability = registry.get(job.capability_id)
    if capability is None:
        return ReauthorizationResult(
            False, "capability_not_registered", "Capability is not registered."
        )
    if capability.manifest.connector_id != job.connector_id:
        return ReauthorizationResult(
            False, "connector_drift", "Capability connector identity has changed."
        )
    if capability.manifest.version != job.connector_version:
        return ReauthorizationResult(
            False, "connector_version_drift", "Connector version has changed."
        )
    if job.plan is not None and job.plan.approval_required:
        if job.approval is None:
            return ReauthorizationResult(
                False, "approval_required", "Exact plan approval is required."
            )
        if not job.approval.matches(job.plan, now=now):
            return ReauthorizationResult(
                False, "approval_invalid", "Plan approval is expired or does not match."
            )
    request = PermissionRequest(
        f"job:{job.job_id}",
        job.principal,
        job.purpose,
        job.capability_id,
        job.operation,
        job.security_domain,
        job.classification,
        job.resource_scope,
    )
    authority = evaluate_capability_use(registry, evaluator, request, now=now)
    if not authority.is_usable:
        return ReauthorizationResult(
            False, authority.reason_code, authority.explanation, authority
        )
    return ReauthorizationResult(
        True, "reauthorized", "Execution authority is currently usable.", authority
    )


class JobService:
    def __init__(self, store: JobStore) -> None:
        self._store = store

    def create(self, job: Job, *, actor_id: str | None = None) -> None:
        if job.status not in {
            JobStatus.PLANNED,
            JobStatus.AWAITING_APPROVAL,
            JobStatus.READY,
        }:
            raise ValueError("new job must begin in a pre-execution status")
        self._store.create(
            job,
            _event(
                job,
                "job_created",
                job.created_at,
                actor_id=actor_id,
                new_status=job.status,
            ),
        )
        if job.plan is not None:
            self._store.append_event(
                _event(
                    job,
                    "plan_bound",
                    job.created_at,
                    actor_id=actor_id,
                    metadata=(("plan_hash", job.plan.plan_hash),),
                )
            )

    def bind_approval(
        self,
        job_id: str,
        approval: ApprovalBinding,
        *,
        now: datetime,
        actor_id: str,
    ) -> Job:
        job = self._required(job_id)
        if job.status is not JobStatus.AWAITING_APPROVAL or job.plan is None:
            raise RuntimeError("job is not awaiting plan approval")
        if not approval.matches(job.plan, now=now):
            raise ValueError("approval does not match the exact current plan")
        updated = replace(
            job,
            approval=approval,
            authority_ref=approval.approval_ref,
            status=JobStatus.READY,
            updated_at=now,
        )
        self._store.transition(
            updated,
            expected_statuses=frozenset({JobStatus.AWAITING_APPROVAL}),
            event=_event(
                updated,
                "approval_bound",
                now,
                actor_id=actor_id,
                previous_status=job.status,
                new_status=updated.status,
                metadata=(("plan_hash", approval.plan_hash),),
            ),
        )
        return updated

    def pause(self, job_id: str, *, now: datetime, actor_id: str) -> Job:
        return self._simple_transition(
            job_id,
            allowed=frozenset({JobStatus.READY, JobStatus.RETRY_WAIT}),
            target=JobStatus.PAUSED,
            event_type="job_paused",
            now=now,
            actor_id=actor_id,
        )

    def cancel(self, job_id: str, *, now: datetime, actor_id: str) -> Job:
        return self._simple_transition(
            job_id,
            allowed=frozenset(
                {
                    JobStatus.PLANNED,
                    JobStatus.AWAITING_APPROVAL,
                    JobStatus.READY,
                    JobStatus.PAUSED,
                    JobStatus.RETRY_WAIT,
                    JobStatus.BLOCKED,
                }
            ),
            target=JobStatus.CANCELLED,
            event_type="job_cancelled",
            now=now,
            actor_id=actor_id,
        )

    def resume(self, job_id: str, *, now: datetime, actor_id: str) -> Job:
        return self._simple_transition(
            job_id,
            allowed=frozenset({JobStatus.PAUSED, JobStatus.BLOCKED}),
            target=JobStatus.READY,
            event_type="job_resumed",
            now=now,
            actor_id=actor_id,
        )

    def recover_interrupted(self, job_id: str, *, now: datetime, actor_id: str) -> Job:
        """Requeue a stranded running job only from a persisted durable boundary."""
        job = self._required(job_id)
        if job.status is not JobStatus.RUNNING:
            raise RuntimeError("only a running job may be recovered")
        checkpoint = self._store.checkpoint(job_id)
        if checkpoint is None or checkpoint.checkpoint_id != job.checkpoint_id:
            raise RuntimeError("interrupted job has no matching durable checkpoint")
        recovered = replace(job, status=JobStatus.READY, updated_at=now)
        self._store.transition(
            recovered,
            expected_statuses=frozenset({JobStatus.RUNNING}),
            event=_event(
                recovered,
                "job_resumed",
                now,
                actor_id=actor_id,
                previous_status=JobStatus.RUNNING,
                new_status=JobStatus.READY,
                reason_code="worker_interrupted",
            ),
            attempt_outcome="interrupted",
            attempt_error_code="worker_interrupted",
        )
        return recovered

    def _simple_transition(
        self,
        job_id: str,
        *,
        allowed: frozenset[JobStatus],
        target: JobStatus,
        event_type: str,
        now: datetime,
        actor_id: str,
    ) -> Job:
        job = self._required(job_id)
        if job.status not in allowed:
            raise RuntimeError("job status does not allow this transition")
        updated = replace(job, status=target, updated_at=now)
        self._store.transition(
            updated,
            expected_statuses=allowed,
            event=_event(
                updated,
                event_type,
                now,
                actor_id=actor_id,
                previous_status=job.status,
                new_status=target,
            ),
        )
        return updated

    def _required(self, job_id: str) -> Job:
        job = self._store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job


def make_event(
    job: Job,
    event_type: str,
    now: datetime,
    *,
    actor_id: str | None = None,
    previous_status: JobStatus | None = None,
    new_status: JobStatus | None = None,
    reason_code: str | None = None,
    metadata: tuple[tuple[str, str | int | bool | None], ...] = (),
) -> AuditEvent:
    return _event(
        job,
        event_type,
        now,
        actor_id=actor_id,
        previous_status=previous_status,
        new_status=new_status,
        reason_code=reason_code,
        metadata=metadata,
    )


def _event(
    job: Job,
    event_type: str,
    now: datetime,
    *,
    actor_id: str | None = None,
    previous_status: JobStatus | None = None,
    new_status: JobStatus | None = None,
    reason_code: str | None = None,
    metadata: tuple[tuple[str, str | int | bool | None], ...] = (),
) -> AuditEvent:
    return AuditEvent(
        f"event:{uuid4().hex}",
        job.job_id,
        event_type,
        now,
        job.correlation_id,
        actor_id,
        previous_status,
        new_status,
        reason_code,
        metadata,
    )
