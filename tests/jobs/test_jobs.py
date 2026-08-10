from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edn.connectors import (
    ActionResult,
    Checkpoint,
    ConnectorManifest,
    ConnectorPlan,
    ConnectorRequest,
    IngestResult,
    PermissionDeniedError,
    SearchResult,
    TransientConnectorError,
    VerificationResult,
    VerificationStatus,
)
from edn.core import (
    AuthenticationStatus,
    CapabilityManifest,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    Classification,
    PermissionEvaluator,
    PermissionOutcome,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
)
from edn.jobs import (
    ApprovalBinding,
    AuditEvent,
    Job,
    JobProgress,
    JobService,
    JobStatus,
    JobStore,
    JobType,
    LocalJobWorker,
    RetryPolicy,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
CONFIG_HASH = "c" * 64


def capability(
    connector_id: str, capability_id: str, operations: frozenset[str]
) -> CapabilityManifest:
    return CapabilityManifest(
        capability_id,
        "synthetic-provider",
        connector_id,
        "1.0.0",
        operations,
        frozenset({"synthetic.permission"}),
        frozenset({"TEST", "EDN", "PERSONAL", "CLIENT:a", "CLIENT:b"}),
        "read",
    )


def manifest(connector_id: str, item: CapabilityManifest) -> ConnectorManifest:
    return ConnectorManifest(
        connector_id,
        "1.0.0",
        connector_id,
        "synthetic-provider",
        "Synthetic job connector.",
        "synthetic",
        (item,),
        item.operations,
        f"urn:schema:{connector_id}:1",
        "1.0.0",
    )


INGEST_CAPABILITY = capability(
    "resumable-ingest", "synthetic.ingest", frozenset({"ingest", "verify"})
)
SEARCH_CAPABILITY = capability(
    "synthetic-search", "synthetic.search", frozenset({"search", "verify"})
)
ACTION_CAPABILITY = capability(
    "synthetic-action", "synthetic.action", frozenset({"act", "verify"})
)


class ResumableIngestConnector:
    manifest = manifest("resumable-ingest", INGEST_CAPABILITY)

    def __init__(self, output_database: Path) -> None:
        self._output_database = output_database
        with sqlite3.connect(output_database) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS output_items(id INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS failure_marker(id INTEGER PRIMARY KEY);
                """
            )

    def ingest(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> IngestResult:
        start = 0 if checkpoint is None else checkpoint.durable_items
        if start == 40:
            with sqlite3.connect(self._output_database) as connection:
                failed = connection.execute(
                    "SELECT 1 FROM failure_marker WHERE id = 1"
                ).fetchone()
            if failed is None:
                connection = sqlite3.connect(self._output_database)
                try:
                    connection.execute("BEGIN")
                    for item in range(41, 48):
                        connection.execute(
                            "INSERT OR IGNORE INTO output_items(id) VALUES (?)", (item,)
                        )
                    connection.rollback()
                finally:
                    connection.close()
                with sqlite3.connect(self._output_database) as connection:
                    connection.execute("INSERT INTO failure_marker(id) VALUES (1)")
                raise TransientConnectorError("Synthetic interruption after item 47.")
        boundary = min(start + 20, 100)
        with sqlite3.connect(self._output_database) as connection:
            for item in range(start + 1, boundary + 1):
                connection.execute(
                    "INSERT OR IGNORE INTO output_items(id) VALUES (?)", (item,)
                )
        if boundary == 100:
            return IngestResult(
                request.request_id, (), processed_items=100, total_items=100
            )
        next_checkpoint = Checkpoint(
            f"checkpoint:{boundary}",
            self.manifest.connector_id,
            self.manifest.version,
            CONFIG_HASH,
            "ingest",
            request.scope,
            f"item:{boundary}",
            boundary,
            NOW + timedelta(seconds=boundary),
        )
        return IngestResult(
            request.request_id,
            (),
            next_checkpoint,
            boundary,
            100,
            False,
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        with sqlite3.connect(self._output_database) as connection:
            count = int(
                connection.execute("SELECT COUNT(*) FROM output_items").fetchone()[0]
            )
        status = (
            VerificationStatus.VERIFIED if count == 100 else VerificationStatus.FAILED
        )
        return VerificationResult(
            request.request_id, status, "Synthetic count verification.", 100, count
        )


class SearchConnector:
    manifest = manifest("synthetic-search", SEARCH_CAPABILITY)

    def __init__(
        self, verification: VerificationStatus = VerificationStatus.VERIFIED
    ) -> None:
        self._verification = verification

    def search(self, request: ConnectorRequest) -> SearchResult:
        return SearchResult(request.request_id, ())

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        return VerificationResult(
            request.request_id, self._verification, "Synthetic verification."
        )


class PermanentFailureConnector(SearchConnector):
    def search(self, request: ConnectorRequest) -> SearchResult:
        raise PermissionDeniedError("Synthetic permission denial.")


class TransientFailureConnector(SearchConnector):
    def search(self, request: ConnectorRequest) -> SearchResult:
        raise TransientConnectorError("Synthetic transient failure.")


class ActionConnector:
    manifest = manifest("synthetic-action", ACTION_CAPABILITY)

    def act(
        self, request: ConnectorRequest, approved_plan: ConnectorPlan
    ) -> ActionResult:
        verification = VerificationResult(
            request.request_id,
            VerificationStatus.VERIFIED,
            "Synthetic action verification.",
        )
        return ActionResult(
            request.request_id,
            approved_plan.plan_id,
            approved_plan.plan_hash,
            1,
            verification,
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        return VerificationResult(
            request.request_id, VerificationStatus.VERIFIED, "Verified."
        )


def security(
    requested_domain: str = "TEST",
    *,
    active_domain: str | None = None,
    tenant: str = "tenant-test",
) -> tuple[PrincipalContext, SecurityDomain, Classification]:
    requested = SecurityDomain(requested_domain, requested_domain, tenant)
    active = SecurityDomain(
        active_domain or requested_domain, active_domain or requested_domain, tenant
    )
    principal = PrincipalContext("principal-one", tenant, frozenset({active}), True)
    return principal, requested, Classification("test-scheme", "internal", "Internal")


def make_job(
    connector_id: str,
    capability_id: str,
    operation: str,
    *,
    job_id: str = "job-one",
    requested_domain: str = "TEST",
    active_domain: str | None = None,
    status: JobStatus = JobStatus.READY,
    plan: ConnectorPlan | None = None,
    approval: ApprovalBinding | None = None,
    configuration_hash: str = CONFIG_HASH,
) -> Job:
    principal, domain, classification = security(
        requested_domain, active_domain=active_domain
    )
    job_type = {
        "ingest": JobType.INGESTION,
        "search": JobType.SEARCH,
        "act": JobType.ACTION,
    }[operation]
    return Job(
        job_id,
        job_type,
        connector_id,
        "1.0.0",
        configuration_hash,
        capability_id,
        operation,
        principal,
        Purpose("test", "Synthetic test"),
        domain,
        classification,
        ("scope-one",),
        f"correlation:{job_id}",
        NOW,
        NOW,
        status,
        RetryPolicy(10, 1.0),
        JobProgress("ready", total_items=100 if operation == "ingest" else None),
        plan,
        approval,
    )


def runtime_registry(
    item: CapabilityManifest, *, ready: bool = True
) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        item,
        CapabilityRuntimeState(
            CapabilityStatus.READY if ready else CapabilityStatus.UNAVAILABLE,
            AuthenticationStatus.NOT_REQUIRED,
            health="healthy" if ready else "unknown",
            last_verified_at=NOW,
        ),
    )
    return registry


def policies(
    item: CapabilityManifest,
    operation: str,
    *,
    outcome: PermissionOutcome = PermissionOutcome.ALLOWED,
    domain_id: str = "TEST",
    expires_at: datetime | None = None,
) -> PermissionEvaluator:
    approval_ref = (
        "approval-policy" if outcome is PermissionOutcome.TEMPORARILY_ALLOWED else None
    )
    rule = PolicyRule(
        "job-policy",
        outcome,
        "Synthetic job policy.",
        tenant_ids=frozenset({"tenant-test"}),
        domain_ids=frozenset({domain_id}),
        capability_ids=frozenset({item.capability_id}),
        operations=frozenset({operation}),
        expires_at=expires_at,
        approval_ref=approval_ref,
    )
    return PermissionEvaluator(PolicySet("jobs-policy", "1.0.0", (rule,)))


def worker(
    store: JobStore,
    connector: object,
    item: CapabilityManifest,
    operation: str,
    *,
    evaluator: PermissionEvaluator | None = None,
    ready: bool = True,
    configuration_hash: str = CONFIG_HASH,
) -> LocalJobWorker:
    return LocalJobWorker(
        store,
        runtime_registry(item, ready=ready),
        evaluator or policies(item, operation),
        (connector,),  # type: ignore[arg-type]
        worker_id="worker-one",
        configuration_hashes={connector.manifest.connector_id: configuration_hash},  # type: ignore[attr-defined]
    )


def create_store(path: Path) -> JobStore:
    store = JobStore(path)
    store.initialise()
    return store


def test_job_persistence_round_trip_schema_and_read_only(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    store = create_store(database)
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job, actor_id="principal-one")
    reconstructed = JobStore(database)
    reconstructed.check_schema()
    assert reconstructed.get(job.job_id) == job
    assert reconstructed.list(statuses=frozenset({JobStatus.READY})) == (job,)
    read_only = JobStore(database, read_only=True)
    assert read_only.get(job.job_id) == job
    with pytest.raises(sqlite3.OperationalError):
        read_only.initialise()


def test_resumable_ingestion_survives_worker_reconstruction(tmp_path: Path) -> None:
    jobs_database = tmp_path / "jobs.db"
    output_database = tmp_path / "output.db"
    store = create_store(jobs_database)
    job = make_job("resumable-ingest", "synthetic.ingest", "ingest")
    JobService(store).create(job)
    first_worker = worker(
        store, ResumableIngestConnector(output_database), INGEST_CAPABILITY, "ingest"
    )
    assert first_worker.run_next(now=NOW).progress.processed_items == 20  # type: ignore[union-attr]
    assert (
        first_worker.run_next(now=NOW + timedelta(seconds=1)).progress.processed_items
        == 40
    )  # type: ignore[union-attr]
    interrupted = first_worker.run_next(now=NOW + timedelta(seconds=2))
    assert interrupted is not None and interrupted.status is JobStatus.RETRY_WAIT
    assert store.checkpoint(job.job_id).durable_items == 40  # type: ignore[union-attr]
    with sqlite3.connect(output_database) as connection:
        assert (
            int(connection.execute("SELECT COUNT(*) FROM output_items").fetchone()[0])
            == 40
        )

    reconstructed_store = JobStore(jobs_database)
    reconstructed_worker = worker(
        reconstructed_store,
        ResumableIngestConnector(output_database),
        INGEST_CAPABILITY,
        "ingest",
    )
    for offset in (6, 7, 8):
        final = reconstructed_worker.run_next(now=NOW + timedelta(seconds=offset))
    assert final is not None and final.status is JobStatus.COMPLETED
    assert final.result is not None and final.result.item_count == 100
    with sqlite3.connect(output_database) as connection:
        assert (
            int(connection.execute("SELECT COUNT(*) FROM output_items").fetchone()[0])
            == 100
        )
    history = reconstructed_store.history(job.job_id)
    event_types = [event.event_type for event in history]
    assert event_types.count("checkpoint_saved") == 4
    assert "retry_scheduled" in event_types
    assert event_types[-1] == "job_completed"


def test_non_resumable_search_completes_and_is_not_reclaimed(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    local_worker = worker(store, SearchConnector(), SEARCH_CAPABILITY, "search")
    completed = local_worker.run_next(now=NOW)
    assert completed is not None and completed.status is JobStatus.COMPLETED
    assert local_worker.run_next(now=NOW + timedelta(seconds=1)) is None


def test_approval_plan_binding_and_action_execution(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    plan = ConnectorPlan(
        "plan-one",
        "synthetic-action",
        "1.0.0",
        "synthetic.action",
        "act",
        ("scope-one",),
        ("synthetic.permission",),
        ("create synthetic record",),
        "external_side_effect",
        (),
        True,
        1,
        0,
    )
    job = make_job(
        "synthetic-action",
        "synthetic.action",
        "act",
        status=JobStatus.AWAITING_APPROVAL,
        plan=plan,
    )
    service = JobService(store)
    service.create(job)
    with pytest.raises(ValueError, match="exact current plan"):
        service.bind_approval(
            job.job_id,
            ApprovalBinding("approval-one", plan.plan_id, "d" * 64, plan.scope),
            now=NOW,
            actor_id="principal-one",
        )
    approved = service.bind_approval(
        job.job_id,
        ApprovalBinding("approval-one", plan.plan_id, plan.plan_hash, plan.scope),
        now=NOW,
        actor_id="principal-one",
    )
    assert approved.status is JobStatus.READY
    completed = worker(store, ActionConnector(), ACTION_CAPABILITY, "act").run_next(
        now=NOW
    )
    assert completed is not None and completed.status is JobStatus.COMPLETED


def test_permanent_failure_is_not_retried(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    failed = worker(
        store, PermanentFailureConnector(), SEARCH_CAPABILITY, "search"
    ).run_next(now=NOW)
    assert failed is not None and failed.status is JobStatus.FAILED
    assert failed.next_retry_at is None
    assert failed.error is not None and not failed.error.retryable


def test_transient_retry_exhaustion_is_bounded(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = replace(
        make_job("synthetic-search", "synthetic.search", "search"),
        retry_policy=RetryPolicy(2, 1.0),
    )
    JobService(store).create(job)
    local_worker = worker(
        store, TransientFailureConnector(), SEARCH_CAPABILITY, "search"
    )
    first = local_worker.run_next(now=NOW)
    assert first is not None and first.status is JobStatus.RETRY_WAIT
    exhausted = local_worker.run_next(now=NOW + timedelta(seconds=1))
    assert exhausted is not None and exhausted.status is JobStatus.FAILED
    assert exhausted.attempt_count == 2
    assert store.metrics().retry_count == 1


def test_indeterminate_verification_never_completes(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    result = worker(
        store,
        SearchConnector(VerificationStatus.INDETERMINATE),
        SEARCH_CAPABILITY,
        "search",
    ).run_next(now=NOW)
    assert result is not None and result.status is JobStatus.INDETERMINATE
    assert result.verification_status is VerificationStatus.INDETERMINATE


@pytest.mark.parametrize(
    ("requested", "active"), [("PERSONAL", "EDN"), ("CLIENT:a", "CLIENT:b")]
)
def test_cross_domain_job_is_blocked_before_claim(
    tmp_path: Path, requested: str, active: str
) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job(
        "synthetic-search",
        "synthetic.search",
        "search",
        requested_domain=requested,
        active_domain=active,
    )
    JobService(store).create(job)
    result = worker(
        store,
        SearchConnector(),
        SEARCH_CAPABILITY,
        "search",
        evaluator=policies(SEARCH_CAPABILITY, "search", domain_id=requested),
    ).run_next(now=NOW)
    assert result is not None and result.status is JobStatus.BLOCKED
    assert "job_claimed" not in {
        event.event_type for event in store.history(job.job_id)
    }


def test_expired_temporary_authority_prevents_resume(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    expired_policy = policies(
        SEARCH_CAPABILITY,
        "search",
        outcome=PermissionOutcome.TEMPORARILY_ALLOWED,
        expires_at=NOW - timedelta(seconds=1),
    )
    result = worker(
        store,
        SearchConnector(),
        SEARCH_CAPABILITY,
        "search",
        evaluator=expired_policy,
    ).run_next(now=NOW)
    assert result is not None and result.status is JobStatus.BLOCKED
    assert result.error is not None and "indeterminate" in result.error.code


def test_prohibited_or_unavailable_capability_cannot_execute(tmp_path: Path) -> None:
    for suffix, evaluator, ready in (
        (
            "prohibited",
            policies(SEARCH_CAPABILITY, "search", outcome=PermissionOutcome.PROHIBITED),
            True,
        ),
        ("unavailable", policies(SEARCH_CAPABILITY, "search"), False),
    ):
        store = create_store(tmp_path / f"{suffix}.db")
        job = make_job(
            "synthetic-search", "synthetic.search", "search", job_id=f"job-{suffix}"
        )
        JobService(store).create(job)
        result = worker(
            store,
            SearchConnector(),
            SEARCH_CAPABILITY,
            "search",
            evaluator=evaluator,
            ready=ready,
        ).run_next(now=NOW)
        assert result is not None and result.status is JobStatus.BLOCKED
        assert "job_claimed" not in {
            event.event_type for event in store.history(job.job_id)
        }


def test_configuration_drift_blocks_checkpoint_resume(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("resumable-ingest", "synthetic.ingest", "ingest")
    JobService(store).create(job)
    connector = ResumableIngestConnector(tmp_path / "output.db")
    first = worker(store, connector, INGEST_CAPABILITY, "ingest").run_next(now=NOW)
    assert first is not None and first.checkpoint_id is not None
    blocked = worker(
        store,
        connector,
        INGEST_CAPABILITY,
        "ingest",
        configuration_hash="d" * 64,
    ).run_next(now=NOW + timedelta(seconds=1))
    assert blocked is not None and blocked.status is JobStatus.BLOCKED
    assert blocked.error is not None and blocked.error.code == "configuration_drift"


def test_connector_version_drift_blocks_execution(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    changed = replace(SEARCH_CAPABILITY, version="2.0.0")
    result = worker(
        store,
        SearchConnector(),
        changed,
        "search",
        evaluator=policies(changed, "search"),
    ).run_next(now=NOW)
    assert result is not None and result.status is JobStatus.BLOCKED
    assert result.error is not None and result.error.code == "connector_version_drift"


def test_pause_resume_and_cancel_transitions_are_persisted(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    service = JobService(store)
    service.create(job)
    paused = service.pause(job.job_id, now=NOW, actor_id="principal-one")
    assert paused.status is JobStatus.PAUSED
    resumed = service.resume(
        job.job_id, now=NOW + timedelta(seconds=1), actor_id="principal-one"
    )
    assert resumed.status is JobStatus.READY
    cancelled = service.cancel(
        job.job_id, now=NOW + timedelta(seconds=2), actor_id="principal-one"
    )
    assert cancelled.status is JobStatus.CANCELLED
    assert [event.event_type for event in store.history(job.job_id)] == [
        "job_created",
        "job_paused",
        "job_resumed",
        "job_cancelled",
    ]


def test_hard_interruption_can_recover_only_from_persisted_checkpoint(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.db"
    store = create_store(database)
    job = make_job("resumable-ingest", "synthetic.ingest", "ingest")
    JobService(store).create(job)
    connector = ResumableIngestConnector(tmp_path / "output.db")
    checkpointed = worker(store, connector, INGEST_CAPABILITY, "ingest").run_next(
        now=NOW
    )
    assert checkpointed is not None and checkpointed.status is JobStatus.READY
    claimed = store.claim(
        job.job_id,
        worker_id="worker-that-stopped",
        now=NOW + timedelta(seconds=1),
        event=AuditEvent(
            "event-hard-claim",
            job.job_id,
            "job_claimed",
            NOW + timedelta(seconds=1),
            job.correlation_id,
            "worker-that-stopped",
            JobStatus.READY,
            JobStatus.RUNNING,
        ),
    )
    assert claimed is not None and claimed.status is JobStatus.RUNNING

    reconstructed = JobStore(database)
    recovered = JobService(reconstructed).recover_interrupted(
        job.job_id,
        now=NOW + timedelta(seconds=2),
        actor_id="principal-one",
    )
    assert recovered.status is JobStatus.READY
    assert reconstructed.attempts(job.job_id)[-1].outcome == "interrupted"


def test_audit_is_append_only_and_rejects_content_metadata(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    store = create_store(database)
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    with pytest.raises(ValueError, match="sensitive"):
        AuditEvent(
            "event-bad",
            job.job_id,
            "bad-event",
            NOW,
            job.correlation_id,
            metadata=(("email_body", "classified source text"),),
        )
    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE audit_events SET event_type = 'changed'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM audit_events")
    assert "classified source text" not in database.read_bytes().decode(
        "utf-8", errors="ignore"
    )


def test_observability_metrics_and_attempt_history(tmp_path: Path) -> None:
    store = create_store(tmp_path / "jobs.db")
    job = make_job("synthetic-search", "synthetic.search", "search")
    JobService(store).create(job)
    worker(store, PermanentFailureConnector(), SEARCH_CAPABILITY, "search").run_next(
        now=NOW
    )
    metrics = store.metrics()
    assert (JobStatus.FAILED, 1) in metrics.status_counts
    assert metrics.failure_reason_counts == (("permission_denied", 1),)
    attempts = store.attempts(job.job_id)
    assert len(attempts) == 1 and attempts[0].outcome == "failed"


def test_unknown_newer_schema_fails_safely(tmp_path: Path) -> None:
    database = tmp_path / "jobs.db"
    store = create_store(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE schema_metadata SET version = 999 WHERE component = 'jobs'"
        )
    with pytest.raises(RuntimeError, match="unsupported"):
        store.check_schema()
