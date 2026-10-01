"""Bounded plan/build/test/review/repair development orchestration."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from edn.development.agent import DevelopmentAgent, DevelopmentValidator
from edn.development.audit import DevelopmentAuditSink
from edn.development.authority import DevelopmentAuthorityPolicy
from edn.development.models import (
    AuditEvent,
    AuthorityOutcome,
    DevelopmentState,
    DevelopmentTask,
    EscalationRequest,
    RepositorySnapshot,
    ReviewDisposition,
    RunLimits,
    RunReport,
    ValidationResult,
)
from edn.development.review import DevelopmentReviewer
from edn.development.roadmap import DevelopmentRoadmap
from edn.development.state import DevelopmentStateStore, validate_repository


class RepositoryInspector(Protocol):
    def snapshot(self) -> RepositorySnapshot: ...


class AutonomousDevelopmentOrchestrator:
    def __init__(
        self,
        state_store: DevelopmentStateStore,
        roadmap: DevelopmentRoadmap,
        policy: DevelopmentAuthorityPolicy,
        repository: RepositoryInspector,
        agent: DevelopmentAgent,
        validator: DevelopmentValidator,
        reviewer: DevelopmentReviewer,
        audit: DevelopmentAuditSink,
        *,
        limits: RunLimits | None = None,
    ) -> None:
        self.state_store = state_store
        self.roadmap = roadmap
        self.policy = policy
        self.repository = repository
        self.agent = agent
        self.validator = validator
        self.reviewer = reviewer
        self.audit = audit
        self.limits = limits or RunLimits()
        self._audit_count = 0

    def run(self) -> RunReport:
        started = time.monotonic()
        state = self.state_store.load()
        repository_failures = validate_repository(state, self.repository.snapshot())
        if repository_failures:
            self._record(
                None,
                "repository_blocked",
                "unexpected_repository_state",
                "blocked",
            )
            return RunReport(
                (), "unexpected_repository_state", audit_events=self._audit_count
            )

        completed: list[str] = []
        commits: list[str] = []
        excluded: set[str] = set()
        pending_escalation: EscalationRequest | None = None
        while len(completed) < self.limits.max_tasks:
            if time.monotonic() - started >= self.limits.max_elapsed_seconds:
                return RunReport(
                    tuple(completed),
                    "elapsed_budget_exhausted",
                    pending_escalation,
                    tuple(commits),
                    self._audit_count,
                )
            task, escalation = self._select(state, frozenset(excluded))
            if task is None:
                return RunReport(
                    tuple(completed),
                    "owner_authority_required" if escalation else "no_eligible_task",
                    escalation or pending_escalation,
                    tuple(commits),
                    self._audit_count,
                )
            pending_escalation = pending_escalation or escalation
            excluded.add(task.task_id)
            result = self._execute_task(task)
            if isinstance(result, EscalationRequest):
                return RunReport(
                    tuple(completed),
                    "owner_authority_required",
                    result,
                    tuple(commits),
                    self._audit_count,
                )
            if result is None:
                continue
            completed.append(task.task_id)
            if result:
                commits.append(result)
            state = self._complete_state(state, task)
            self.state_store.save(state)
            self._record(task, "task_completed", "acceptance_passed", "completed")
        return RunReport(
            tuple(completed),
            "task_budget_reached",
            pending_escalation,
            tuple(commits),
            self._audit_count,
        )

    def _select(
        self, state: DevelopmentState, excluded: frozenset[str]
    ) -> tuple[DevelopmentTask | None, EscalationRequest | None]:
        first_escalation = None
        for task in self.roadmap.eligible_tasks(state, excluded=excluded):
            decision = self.policy.evaluate(task.authority_actions)
            self._record(
                task,
                "authority_evaluated",
                decision.reason_code,
                decision.outcome.value,
            )
            if decision.outcome is AuthorityOutcome.ALLOWED:
                self._record(task, "task_selected", "standing_authority", "selected")
                return task, first_escalation
            if first_escalation is None:
                first_escalation = self.policy.escalation_for(task, decision)
            self._record(task, "task_blocked", decision.reason_code, "blocked")
        return None, first_escalation

    def _execute_task(self, task: DevelopmentTask) -> str | EscalationRequest | None:
        signatures: dict[str, int] = {}
        self._record(task, "implementation_started", "task_selected", "started")
        for repair_cycle in range(self.limits.max_repair_cycles + 1):
            agent_result = self.agent.implement(task, repair_cycle=repair_cycle)
            if agent_result.success:
                validation = self.validator.validate(task)
            else:
                validation = ValidationResult(
                    False,
                    (agent_result.summary,),
                    failure_signature=agent_result.failure_signature,
                )
            self._record(
                task,
                "validation_executed",
                "validation_passed" if validation.passed else "validation_failed",
                "passed" if validation.passed else "failed",
                validation.evidence,
            )
            review = self.reviewer.review(task, validation)
            owner_findings = tuple(
                item
                for item in review.findings
                if item.disposition is ReviewDisposition.OWNER_REQUIRED
            )
            if owner_findings:
                finding = owner_findings[0]
                self._record(task, "review_result", finding.code, "owner_required")
                return EscalationRequest(
                    f"{task.task_id}: {finding.explanation}",
                    "Reviewer identified an owner-level boundary.",
                    "Approve or decline the material finding only.",
                    "Builder repairs or continues within the approved boundary.",
                    "Task remains blocked; another eligible task may be selected.",
                    finding.code,
                    True,
                    "Review architecture and authority impact before approval.",
                )
            if validation.passed and review.passed:
                self._record(task, "review_result", "review_passed", "passed")
                return agent_result.recommended_commit
            signature = validation.failure_signature or "review_failure"
            signatures[signature] = signatures.get(signature, 0) + 1
            if signatures[signature] >= self.limits.repeated_failure_limit:
                self._record(
                    task, "task_blocked", "repeated_identical_failure", "blocked"
                )
                return None
            if repair_cycle >= self.limits.max_repair_cycles:
                self._record(task, "task_blocked", "repair_budget_exhausted", "blocked")
                return None
            self._record(task, "repair_attempted", signature, "repairing")
        return None

    @staticmethod
    def _complete_state(
        state: DevelopmentState, task: DevelopmentTask
    ) -> DevelopmentState:
        completed = tuple(dict.fromkeys((*state.completed_increments, task.task_id)))
        successor = task.successor_tasks[0] if task.successor_tasks else None
        return replace(
            state,
            completed_increments=completed,
            active_increment=None,
            next_recommended_increment=successor,
            updated_at=datetime.now(UTC),
            provenance=f"orchestrator:{task.task_id}",
        )

    def _record(
        self,
        task: DevelopmentTask | None,
        event_type: str,
        reason_code: str,
        outcome: str,
        evidence: tuple[str, ...] = (),
    ) -> None:
        self.audit.append(
            AuditEvent(
                f"dev-event:{uuid4().hex}",
                event_type,
                datetime.now(UTC),
                None if task is None else task.task_id,
                reason_code,
                outcome,
                evidence,
            )
        )
        self._audit_count += 1
