"""One-shot local worker for explicitly supplied connectors and policy state."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast

from edn.connectors import (
    ActionConnector,
    Checkpoint,
    Connector,
    ConnectorError,
    ConnectorRequest,
    DiscoverableConnector,
    IngestibleConnector,
    InspectableConnector,
    InvalidCheckpointError,
    SearchableConnector,
    SyncableConnector,
    VerifiableConnector,
    VerificationStatus,
    require_compatible_checkpoint,
    require_supported_operation,
)
from edn.core import CapabilityRegistry, PermissionEvaluator
from edn.jobs.models import (
    Job,
    JobError,
    JobProgress,
    JobResultRef,
    JobStatus,
)
from edn.jobs.service import make_event, reauthorize_job
from edn.jobs.storage import JobStore


class LocalJobWorker:
    def __init__(
        self,
        store: JobStore,
        registry: CapabilityRegistry,
        evaluator: PermissionEvaluator,
        connectors: tuple[Connector, ...],
        *,
        worker_id: str,
        configuration_hashes: dict[str, str],
    ) -> None:
        self._store = store
        self._registry = registry
        self._evaluator = evaluator
        self._connectors = {
            connector.manifest.connector_id: connector for connector in connectors
        }
        self._worker_id = worker_id
        self._configuration_hashes = dict(configuration_hashes)

    def run_next(self, *, now: datetime) -> Job | None:
        for candidate in self._store.claimable(now=now):
            connector = self._connectors.get(candidate.connector_id)
            if connector is None:
                return self._block(
                    candidate, "connector_unavailable", "Connector is unavailable.", now
                )
            if (
                self._configuration_hashes.get(candidate.connector_id)
                != candidate.configuration_hash
            ):
                return self._block(
                    candidate,
                    "configuration_drift",
                    "Connector configuration no longer matches the job.",
                    now,
                )
            authorization = reauthorize_job(
                candidate, self._registry, self._evaluator, now=now
            )
            if not authorization.usable or authorization.authority is None:
                return self._block(
                    candidate, authorization.reason_code, authorization.explanation, now
                )
            checkpoint = self._store.checkpoint(candidate.job_id)
            try:
                if checkpoint is not None:
                    require_compatible_checkpoint(
                        checkpoint, connector.manifest, candidate.configuration_hash
                    )
            except InvalidCheckpointError as error:
                return self._block(candidate, error.code, error.explanation, now)
            claimed = self._store.claim(
                candidate.job_id,
                worker_id=self._worker_id,
                now=now,
                event=make_event(
                    candidate,
                    "job_claimed",
                    now,
                    actor_id=self._worker_id,
                    previous_status=candidate.status,
                    new_status=JobStatus.RUNNING,
                ),
            )
            if claimed is None:
                continue
            request = ConnectorRequest(
                f"execution:{claimed.job_id}",
                claimed.correlation_id,
                claimed.principal,
                claimed.purpose,
                claimed.security_domain,
                claimed.classification,
                claimed.capability_id,
                claimed.operation,
                authorization.authority,
                claimed.resource_scope,
            )
            try:
                return self._execute(claimed, connector, request, checkpoint, now)
            except ConnectorError as error:
                return self._handle_connector_error(claimed, error, now)
        return None

    def _execute(
        self,
        job: Job,
        connector: Connector,
        request: ConnectorRequest,
        checkpoint: Checkpoint | None,
        now: datetime,
    ) -> Job:
        require_supported_operation(connector, request)
        result_ref: JobResultRef
        if job.operation == "ingest":
            typed = cast(IngestibleConnector, connector)
            ingest_result = typed.ingest(request, checkpoint)
            result_ref = JobResultRef(
                "universal_records",
                tuple(record.source_record_key for record in ingest_result.records),
                ingest_result.processed_items,
            )
            if not ingest_result.complete:
                assert ingest_result.checkpoint is not None
                require_compatible_checkpoint(
                    ingest_result.checkpoint,
                    connector.manifest,
                    job.configuration_hash,
                )
                progress = JobProgress(
                    "checkpointed",
                    ingest_result.processed_items,
                    ingest_result.total_items,
                    job.progress.checkpoint_count + 1,
                )
                yielded = replace(
                    job,
                    status=JobStatus.READY,
                    checkpoint_id=ingest_result.checkpoint.checkpoint_id,
                    progress=progress,
                    result=result_ref,
                    updated_at=now,
                )
                self._store.save_checkpoint(
                    yielded,
                    ingest_result.checkpoint,
                    event=make_event(
                        yielded,
                        "checkpoint_saved",
                        now,
                        actor_id=self._worker_id,
                        previous_status=JobStatus.RUNNING,
                        new_status=JobStatus.READY,
                        metadata=(
                            ("durable_items", ingest_result.checkpoint.durable_items),
                        ),
                    ),
                )
                return yielded
        elif job.operation == "sync":
            typed_sync = cast(SyncableConnector, connector)
            sync_result = typed_sync.sync(request, checkpoint)
            result_ref = JobResultRef(
                "universal_records", item_count=sync_result.processed_items
            )
        elif job.operation == "search":
            search_result = cast(SearchableConnector, connector).search(request)
            result_ref = JobResultRef(
                "evidence",
                tuple(item.evidence_id for item in search_result.evidence),
                len(search_result.evidence),
            )
        elif job.operation == "discover":
            discovery_result = cast(DiscoverableConnector, connector).discover(
                request, checkpoint
            )
            result_ref = JobResultRef(
                "resources",
                tuple(item.resource_id for item in discovery_result.resources),
                discovery_result.processed_resources,
            )
            if not discovery_result.complete:
                assert discovery_result.checkpoint is not None
                require_compatible_checkpoint(
                    discovery_result.checkpoint,
                    connector.manifest,
                    job.configuration_hash,
                )
                yielded = replace(
                    job,
                    status=JobStatus.READY,
                    checkpoint_id=discovery_result.checkpoint.checkpoint_id,
                    progress=JobProgress(
                        "checkpointed",
                        discovery_result.processed_resources,
                        None,
                        job.progress.checkpoint_count + 1,
                    ),
                    result=JobResultRef(
                        "resources",
                        item_count=discovery_result.processed_resources,
                    ),
                    updated_at=now,
                )
                self._store.save_checkpoint(
                    yielded,
                    discovery_result.checkpoint,
                    event=make_event(
                        yielded,
                        "checkpoint_saved",
                        now,
                        actor_id=self._worker_id,
                        previous_status=JobStatus.RUNNING,
                        new_status=JobStatus.READY,
                        metadata=(
                            (
                                "durable_items",
                                discovery_result.checkpoint.durable_items,
                            ),
                        ),
                    ),
                )
                return yielded
        elif job.operation == "inspect":
            inspection_result = cast(InspectableConnector, connector).inspect(request)
            result_ref = JobResultRef(
                "inspection", (inspection_result.resource.resource_id,), 1
            )
        elif job.operation == "act":
            if job.plan is None:
                raise ConnectorError(
                    "Action job has no bound plan.", connector_id=job.connector_id
                )
            action_result = cast(ActionConnector, connector).act(request, job.plan)
            result_ref = JobResultRef(
                "action", (action_result.plan_hash,), action_result.changed_items
            )
        else:
            raise ConnectorError(
                "Worker does not support this operation.", connector_id=job.connector_id
            )

        if not isinstance(connector, VerifiableConnector):
            return self._verification_block(
                job, result_ref, now, "verification_not_supported"
            )
        self._store.append_event(
            make_event(
                job,
                "verification_started",
                now,
                actor_id=self._worker_id,
                previous_status=JobStatus.RUNNING,
                new_status=JobStatus.RUNNING,
            )
        )
        verification = connector.verify(request)
        self._store.append_event(
            make_event(
                job,
                "verification_completed",
                now,
                actor_id=self._worker_id,
                previous_status=JobStatus.RUNNING,
                new_status=JobStatus.RUNNING,
                reason_code=verification.status.value,
            )
        )
        if verification.status in {
            VerificationStatus.FAILED,
            VerificationStatus.INDETERMINATE,
        }:
            return self._verification_block(
                job, result_ref, now, f"verification_{verification.status.value}"
            )
        final_status = (
            JobStatus.COMPLETED_WITH_WARNINGS
            if verification.status is VerificationStatus.VERIFIED_WITH_WARNINGS
            else JobStatus.COMPLETED
        )
        completed = replace(
            job,
            status=final_status,
            result=result_ref,
            verification_status=verification.status,
            progress=JobProgress(
                "completed",
                max(job.progress.processed_items, result_ref.item_count),
                job.progress.total_items or result_ref.item_count,
                job.progress.checkpoint_count,
            ),
            updated_at=now,
            completed_at=now,
        )
        self._store.transition(
            completed,
            expected_statuses=frozenset({JobStatus.RUNNING}),
            event=make_event(
                completed,
                "job_completed",
                now,
                actor_id=self._worker_id,
                previous_status=JobStatus.RUNNING,
                new_status=final_status,
                reason_code=verification.status.value,
            ),
            attempt_outcome="completed",
        )
        return completed

    def _handle_connector_error(
        self, job: Job, error: ConnectorError, now: datetime
    ) -> Job:
        retryable = (
            error.transient
            and error.code in job.retry_policy.retryable_error_codes
            and job.attempt_count < job.retry_policy.max_attempts
        )
        safe_error = JobError(error.code, error.explanation, retryable)
        if retryable:
            next_retry = now + timedelta(
                seconds=job.retry_policy.delay_for_attempt(job.attempt_count)
            )
            updated = replace(
                job,
                status=JobStatus.RETRY_WAIT,
                error=safe_error,
                next_retry_at=next_retry,
                updated_at=now,
            )
            event_type = "retry_scheduled"
        else:
            updated = replace(
                job,
                status=JobStatus.FAILED,
                error=safe_error,
                updated_at=now,
                completed_at=now,
            )
            event_type = "job_failed"
        self._store.transition(
            updated,
            expected_statuses=frozenset({JobStatus.RUNNING}),
            event=make_event(
                updated,
                event_type,
                now,
                actor_id=self._worker_id,
                previous_status=JobStatus.RUNNING,
                new_status=updated.status,
                reason_code=error.code,
            ),
            attempt_outcome="retry" if retryable else "failed",
            attempt_error_code=error.code,
        )
        return updated

    def _verification_block(
        self, job: Job, result: JobResultRef, now: datetime, reason: str
    ) -> Job:
        updated = replace(
            job,
            status=JobStatus.INDETERMINATE,
            result=result,
            verification_status=VerificationStatus.INDETERMINATE,
            error=JobError(reason, "Operation could not be verified safely."),
            updated_at=now,
            completed_at=now,
        )
        self._store.transition(
            updated,
            expected_statuses=frozenset({JobStatus.RUNNING}),
            event=make_event(
                updated,
                "job_failed",
                now,
                actor_id=self._worker_id,
                previous_status=JobStatus.RUNNING,
                new_status=JobStatus.INDETERMINATE,
                reason_code=reason,
            ),
            attempt_outcome="indeterminate",
            attempt_error_code=reason,
        )
        return updated

    def _block(self, job: Job, code: str, explanation: str, now: datetime) -> Job:
        blocked = replace(
            job,
            status=JobStatus.BLOCKED,
            error=JobError(code, explanation),
            updated_at=now,
        )
        self._store.transition(
            blocked,
            expected_statuses=frozenset({JobStatus.READY, JobStatus.RETRY_WAIT}),
            event=make_event(
                blocked,
                "job_blocked",
                now,
                actor_id=self._worker_id,
                previous_status=job.status,
                new_status=JobStatus.BLOCKED,
                reason_code=code,
            ),
        )
        return blocked
