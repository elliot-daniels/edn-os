from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edn.connectors import ConnectorRequest, check_connector
from edn.connectors.local_files import (
    ApprovedRoot,
    CandidateState,
    CoverageStatus,
    LocalFilesConfig,
    LocalFilesConnector,
    SymlinkPolicy,
    load_config,
)
from edn.connectors.local_files.cli import main as local_files_main
from edn.core import (
    CapabilityRegistry,
    Classification,
    PermissionEvaluator,
    PermissionOutcome,
    PermissionRequest,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    evaluate_capability_use,
)
from edn.jobs import (
    ApprovalBinding,
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


def make_config(
    base: Path,
    root: Path,
    *,
    domain_id: str = "TEST",
    tenant: str = "tenant-test",
    excluded: tuple[Path, ...] = (),
    discovery_batch: int = 50,
    ingestion_batch: int = 50,
    symlink_policy: SymlinkPolicy = SymlinkPolicy.NEVER,
) -> LocalFilesConfig:
    domain = SecurityDomain(domain_id, domain_id, tenant)
    classification = Classification(f"{tenant}-scheme", "internal", "Internal")
    return LocalFilesConfig(
        (ApprovedRoot("root-one", root.resolve(), domain, classification),),
        (base / "catalogue.db").resolve(),
        (base / "content").resolve(),
        excluded_roots=tuple(path.resolve() for path in excluded),
        excluded_extensions=frozenset({".tmp"}),
        max_file_size_bytes=1024 * 1024,
        symlink_policy=symlink_policy,
        discovery_batch_size=discovery_batch,
        ingestion_batch_size=ingestion_batch,
    )


def capability(connector: LocalFilesConnector, capability_id: str):
    return next(
        item
        for item in connector.manifest.capabilities
        if item.capability_id == capability_id
    )


def registry(connector: LocalFilesConnector) -> CapabilityRegistry:
    result = CapabilityRegistry()
    for item, runtime in connector.runtime_states():
        result.register(item, runtime)
    return result


def evaluator(
    capability_id: str,
    operation: str,
    domain_id: str,
    *,
    outcome: PermissionOutcome = PermissionOutcome.ALLOWED,
) -> PermissionEvaluator:
    return PermissionEvaluator(
        PolicySet(
            "local-files-policy",
            "1.0.0",
            (
                PolicyRule(
                    f"rule:{operation}",
                    outcome,
                    "Synthetic Local Files policy.",
                    tenant_ids=frozenset({"tenant-test", "tenant-two"}),
                    domain_ids=frozenset({domain_id}),
                    capability_ids=frozenset({capability_id}),
                    operations=frozenset({operation}),
                ),
            ),
        )
    )


def context(
    config: LocalFilesConfig, *, active_domain: SecurityDomain | None = None
) -> tuple[PrincipalContext, SecurityDomain, Classification]:
    root = config.roots[0]
    active = active_domain or root.security_domain
    principal = PrincipalContext(
        "principal-one", active.tenant_id or "tenant-test", frozenset({active}), True
    )
    return principal, root.security_domain, root.classification


def authorized_request(
    connector: LocalFilesConnector,
    capability_id: str,
    operation: str,
    scope: tuple[str, ...],
) -> ConnectorRequest:
    principal, domain, classification = context(connector.config)
    permission_request = PermissionRequest(
        f"permission:{operation}",
        principal,
        Purpose("local-files-test", "Synthetic Local Files test"),
        capability_id,
        operation,
        domain,
        classification,
        scope,
    )
    authority = evaluate_capability_use(
        registry(connector),
        evaluator(capability_id, operation, domain.domain_id),
        permission_request,
        now=NOW,
    )
    return ConnectorRequest(
        f"request:{operation}",
        "discovery-run-one",
        principal,
        permission_request.purpose,
        domain,
        classification,
        capability_id,
        operation,
        authority,
        scope,
    )


def make_job(
    connector: LocalFilesConnector,
    capability_id: str,
    operation: str,
    scope: tuple[str, ...],
    *,
    job_id: str,
    status: JobStatus = JobStatus.READY,
    plan=None,
    approval=None,
    principal: PrincipalContext | None = None,
    domain: SecurityDomain | None = None,
) -> Job:
    default_principal, default_domain, classification = context(connector.config)
    selected_domain = domain or default_domain
    return Job(
        job_id,
        JobType.DISCOVERY if operation == "discover" else JobType.INGESTION,
        connector.manifest.connector_id,
        connector.manifest.version,
        connector.config.configuration_hash,
        capability_id,
        operation,
        principal or default_principal,
        Purpose("local-files-test", "Synthetic Local Files test"),
        selected_domain,
        classification,
        scope,
        f"correlation:{job_id}",
        NOW,
        NOW,
        status,
        RetryPolicy(20, 0),
        JobProgress("ready"),
        plan,
        approval,
    )


def run_job(
    store: JobStore,
    connector: LocalFilesConnector,
    job: Job,
    policy: PermissionEvaluator,
) -> Job:
    local_worker = LocalJobWorker(
        store,
        registry(connector),
        policy,
        (connector,),
        worker_id="worker-one",
        configuration_hashes={
            connector.manifest.connector_id: connector.config.configuration_hash
        },
    )
    result: Job | None = None
    for offset in range(30):
        result = local_worker.run_next(now=NOW + timedelta(seconds=offset))
        assert result is not None
        if result.status not in {JobStatus.READY, JobStatus.RETRY_WAIT}:
            return result
    raise AssertionError("job did not reach a terminal state")


def discover_direct(connector: LocalFilesConnector) -> tuple:
    request = authorized_request(
        connector, "local-files.discover", "discover", ("root-one",)
    )
    checkpoint = None
    while True:
        result = connector.discover(request, checkpoint)
        if result.complete:
            break
        checkpoint = result.checkpoint
    return connector.catalogue.candidates_for_run(request.correlation_id)


def test_connector_conforms_and_capabilities_register(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    connector = LocalFilesConnector(make_config(tmp_path, root))
    report = check_connector(connector)
    assert report.conforms, report.issues
    assert {item.capability_id for item in connector.manifest.capabilities} == {
        "local-files.discover",
        "local-files.inspect",
        "local-files.plan",
        "local-files.ingest",
        "local-files.verify",
    }
    assert len(registry(connector).list()) == 5


def test_path_traversal_symlink_escape_and_exclusion_are_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    excluded = root / "excluded"
    outside = tmp_path / "outside"
    excluded.mkdir(parents=True)
    outside.mkdir()
    (excluded / "secret.txt").write_text("excluded content", encoding="utf-8")
    (outside / "outside.txt").write_text("outside content", encoding="utf-8")
    link = root / "escape.txt"
    try:
        link.symlink_to(outside / "outside.txt")
    except OSError:
        pytest.skip("symlinks are unavailable in this environment")
    connector = LocalFilesConnector(make_config(tmp_path, root, excluded=(excluded,)))
    with pytest.raises(ValueError, match="escapes"):
        connector.config.validate_candidate_path(outside / "outside.txt", "root-one")
    assert discover_direct(connector) == ()


def test_discovery_is_metadata_only_and_classifies_missing_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.txt").write_text("do not read during discovery", encoding="utf-8")
    (root / "report.docx").write_bytes(b"synthetic docx bytes")
    (root / "run.exe").write_bytes(b"must never execute")
    executable = root / "do-not-run.sh"
    marker = tmp_path / "execution-marker"
    executable.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    executable.chmod(0o755)
    connector = LocalFilesConnector(make_config(tmp_path, root))

    def forbidden_read(*args: object, **kwargs: object) -> str:
        raise AssertionError("discovery attempted a content read")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    candidates = discover_direct(connector)
    assert len(candidates) == 4
    summary = connector.catalogue.summary("discovery-run-one")
    assert summary.files_discovered == 4
    assert summary.potentially_ingestible == 1
    assert summary.unsupported == 3
    signals = {item.missing_capability for item in summary.unsupported_capabilities}
    assert "document-docx.ingest" in signals
    assert "executable.prohibited" in signals
    assert not marker.exists()


def test_inaccessible_directory_becomes_bounded_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    connector = LocalFilesConnector(make_config(tmp_path, root))

    def inaccessible_scandir(path: Path):
        raise PermissionError("synthetic inaccessible path")

    monkeypatch.setattr(
        "edn.connectors.local_files.traversal.os.scandir", inaccessible_scandir
    )
    result = connector.discover(
        authorized_request(connector, "local-files.discover", "discover", ("root-one",))
    )
    assert result.warnings == ("inaccessible:PermissionError",)
    assert "synthetic inaccessible path" not in result.warnings[0]


def test_coverage_opportunities_expose_dimensions_without_semantic_value(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for index in range(3):
        (root / f"drawing-{index}.svg").write_bytes(b"svg")
    (root / "large.png").write_bytes(b"x" * 10_000)
    (root / "notes.txt").write_text("supported", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root))
    discover_direct(connector)

    summary = connector.catalogue.summary("discovery-run-one")
    opportunities = summary.coverage_opportunities
    svg = next(item for item in opportunities if item.category == "unknown")
    image = next(item for item in opportunities if item.category == "image")
    text = next(item for item in opportunities if item.category == "text")

    assert svg.coverage_rank == 1
    assert svg.status is CoverageStatus.UNKNOWN
    assert svg.record_count == 3
    assert svg.record_percentage == 60.0
    assert svg.extension_counts == ((".svg", 3),)
    assert svg.extension_diversity == 1
    assert svg.deterministic_confidence == "low"
    assert image.coverage_rank == 2
    assert image.status is CoverageStatus.MISSING_INGESTION_CAPABILITY
    assert image.byte_percentage > svg.byte_percentage
    assert text.coverage_rank is None
    assert text.status is CoverageStatus.SUPPORTED_NOW
    assert text.existing_capability == "local-files.ingest"
    assert text.security_domains == ("TEST",)
    assert text.classifications == ("Internal",)
    assert all("semantic value" in item.limitations[0] for item in opportunities)


def test_discovery_job_checkpoints_and_persists_summary(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for index in range(5):
        (root / f"file-{index}.txt").write_text(str(index), encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root, discovery_batch=2))
    store = JobStore(tmp_path / "jobs.db")
    store.initialise()
    job = make_job(
        connector,
        "local-files.discover",
        "discover",
        ("root-one",),
        job_id="discover-job",
    )
    JobService(store).create(job)
    completed = run_job(
        store,
        connector,
        job,
        evaluator("local-files.discover", "discover", "TEST"),
    )
    assert completed.status is JobStatus.COMPLETED
    assert completed.progress.processed_items == 5
    assert completed.progress.checkpoint_count == 2
    assert connector.catalogue.summary(job.correlation_id).files_discovered == 5


def test_inspect_is_bounded_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.md").write_text("private body", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidate = discover_direct(connector)[0]
    result = connector.inspect(
        authorized_request(
            connector, "local-files.inspect", "inspect", (candidate.resource_id,)
        )
    )
    assert result.resource.resource_id == candidate.resource_id
    assert "private body" not in " ".join(result.observations)


def test_plan_hash_binds_selection_and_configuration(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidates = discover_direct(connector)
    first = connector.plan(
        authorized_request(
            connector, "local-files.plan", "plan", (candidates[0].resource_id,)
        )
    )
    second = connector.plan(
        authorized_request(
            connector, "local-files.plan", "plan", (candidates[1].resource_id,)
        )
    )
    assert first.plan_hash != second.plan_hash
    assert first.configuration_hash == connector.config.configuration_hash
    assert first.approval_required


def test_full_vertical_discovery_plan_approval_ingestion_and_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    source_a = root / "a.txt"
    source_b = root / "b.md"
    source_a.write_text("alpha source", encoding="utf-8")
    source_b.write_text("beta source", encoding="utf-8")
    before = {
        path: (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (source_a, source_b)
    }
    connector = LocalFilesConnector(
        make_config(tmp_path, root, discovery_batch=1, ingestion_batch=1)
    )
    store = JobStore(tmp_path / "jobs.db")
    store.initialise()
    discovery = make_job(
        connector,
        "local-files.discover",
        "discover",
        ("root-one",),
        job_id="discover-job",
    )
    JobService(store).create(discovery)
    assert (
        run_job(
            store,
            connector,
            discovery,
            evaluator("local-files.discover", "discover", "TEST"),
        ).status
        is JobStatus.COMPLETED
    )
    candidates = connector.catalogue.candidates_for_run(discovery.correlation_id)
    selected = tuple(item.resource_id for item in candidates)
    plan = connector.plan(
        authorized_request(connector, "local-files.plan", "plan", selected)
    )

    principal, domain, classification = context(connector.config)
    proposed = PermissionRequest(
        "permission-ingest-approval",
        principal,
        Purpose("local-files-test", "Synthetic Local Files test"),
        "local-files.ingest",
        "ingest",
        domain,
        classification,
        selected,
    )
    approval_decision = evaluator(
        "local-files.ingest",
        "ingest",
        "TEST",
        outcome=PermissionOutcome.APPROVAL_REQUIRED,
    ).evaluate(proposed, now=NOW)
    assert approval_decision.outcome is PermissionOutcome.APPROVAL_REQUIRED

    ingestion = make_job(
        connector,
        "local-files.ingest",
        "ingest",
        plan.scope,
        job_id="ingest-job",
        status=JobStatus.AWAITING_APPROVAL,
        plan=plan,
    )
    service = JobService(store)
    service.create(ingestion)
    approved = service.bind_approval(
        ingestion.job_id,
        ApprovalBinding("approval-one", plan.plan_id, plan.plan_hash, plan.scope),
        now=NOW,
        actor_id="principal-one",
    )
    completed = run_job(
        store,
        connector,
        approved,
        evaluator("local-files.ingest", "ingest", "TEST"),
    )
    assert completed.status is JobStatus.COMPLETED
    records = connector.catalogue.records(selected)
    evidence = connector.evidence(selected)
    assert len(records) == len(evidence) == 2
    assert all(record.security_domain.domain_id == "TEST" for record in records)
    assert completed.progress.checkpoint_count == 1
    for path, original in before.items():
        assert (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        ) == original
    audit_text = " ".join(
        event.to_dict().__repr__() for event in store.history(ingestion.job_id)
    )
    assert "alpha source" not in audit_text and "beta source" not in audit_text


def test_changed_source_after_approval_fails_without_silent_ingestion(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    source = root / "change.txt"
    source.write_text("before", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidate = discover_direct(connector)[0]
    plan = connector.plan(
        authorized_request(
            connector, "local-files.plan", "plan", (candidate.resource_id,)
        )
    )
    source.write_text("after material change", encoding="utf-8")
    os.utime(
        source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 1_000_000)
    )
    store = JobStore(tmp_path / "jobs.db")
    store.initialise()
    job = make_job(
        connector,
        "local-files.ingest",
        "ingest",
        plan.scope,
        job_id="changed-job",
        status=JobStatus.READY,
        plan=plan,
        approval=ApprovalBinding(
            "approval-one", plan.plan_id, plan.plan_hash, plan.scope
        ),
    )
    JobService(store).create(job)
    failed = run_job(
        store,
        connector,
        job,
        evaluator("local-files.ingest", "ingest", "TEST"),
    )
    assert failed.status is JobStatus.FAILED
    assert failed.error is not None and failed.error.code == "incompatible_source_state"
    assert (
        connector.catalogue.get(candidate.resource_id).state
        is CandidateState.SOURCE_CHANGED
    )  # type: ignore[union-attr]


def test_approval_for_subset_a_cannot_execute_subset_b(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root))
    candidates = discover_direct(connector)
    plan = connector.plan(
        authorized_request(
            connector, "local-files.plan", "plan", (candidates[0].resource_id,)
        )
    )
    store = JobStore(tmp_path / "jobs.db")
    store.initialise()
    job = make_job(
        connector,
        "local-files.ingest",
        "ingest",
        (candidates[1].resource_id,),
        job_id="scope-drift-job",
        plan=plan,
        approval=ApprovalBinding(
            "approval-one", plan.plan_id, plan.plan_hash, plan.scope
        ),
    )
    JobService(store).create(job)
    blocked = run_job(
        store,
        connector,
        job,
        evaluator("local-files.ingest", "ingest", "TEST"),
    )
    assert blocked.status is JobStatus.BLOCKED
    assert blocked.error is not None and blocked.error.code == "plan_scope_drift"


def test_unauthorized_domain_is_blocked_before_discovery(tmp_path: Path) -> None:
    root = tmp_path / "personal"
    root.mkdir()
    (root / "personal.txt").write_text("personal", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root, domain_id="PERSONAL"))
    edn = SecurityDomain("EDN", "EDN", "tenant-test")
    principal = PrincipalContext("principal-one", "tenant-test", frozenset({edn}), True)
    store = JobStore(tmp_path / "jobs.db")
    store.initialise()
    job = make_job(
        connector,
        "local-files.discover",
        "discover",
        ("root-one",),
        job_id="unauthorized-job",
        principal=principal,
    )
    JobService(store).create(job)
    blocked = run_job(
        store,
        connector,
        job,
        evaluator("local-files.discover", "discover", "PERSONAL"),
    )
    assert blocked.status is JobStatus.BLOCKED
    assert connector.catalogue.candidates_for_run(job.correlation_id) == ()


def test_personal_candidate_cannot_ingest_under_edn_authority(tmp_path: Path) -> None:
    root = tmp_path / "personal"
    root.mkdir()
    (root / "personal.txt").write_text("personal source", encoding="utf-8")
    connector = LocalFilesConnector(make_config(tmp_path, root, domain_id="PERSONAL"))
    candidate = discover_direct(connector)[0]
    plan = connector.plan(
        authorized_request(
            connector, "local-files.plan", "plan", (candidate.resource_id,)
        )
    )
    edn = SecurityDomain("EDN", "EDN", "tenant-test")
    edn_principal = PrincipalContext(
        "edn-principal", "tenant-test", frozenset({edn}), True
    )
    store = JobStore(tmp_path / "jobs.db")
    store.initialise()
    job = make_job(
        connector,
        "local-files.ingest",
        "ingest",
        plan.scope,
        job_id="personal-under-edn",
        plan=plan,
        approval=ApprovalBinding(
            "approval-one", plan.plan_id, plan.plan_hash, plan.scope
        ),
        principal=edn_principal,
        domain=edn,
    )
    JobService(store).create(job)
    blocked = run_job(
        store,
        connector,
        job,
        evaluator("local-files.ingest", "ingest", "EDN"),
    )
    assert blocked.status is JobStatus.BLOCKED
    assert (
        connector.catalogue.get(candidate.resource_id).state
        is CandidateState.DISCOVERED
    )  # type: ignore[union-attr]


def test_second_tenant_has_independent_root_and_domain(tmp_path: Path) -> None:
    root = tmp_path / "tenant-two-root"
    root.mkdir()
    (root / "record.json").write_text('{"tenant": 2}', encoding="utf-8")
    connector = LocalFilesConnector(
        make_config(tmp_path, root, domain_id="WORKSPACE:west", tenant="tenant-two")
    )
    candidates = discover_direct(connector)
    assert len(candidates) == 1
    assert candidates[0].security_domain.tenant_id == "tenant-two"
    assert candidates[0].classification.scheme_id == "tenant-two-scheme"


def test_durable_traversal_reconstructs_without_candidate_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for index in range(6):
        (root / f"file-{index}.txt").write_text("x", encoding="utf-8")
    config = make_config(tmp_path, root, discovery_batch=2)
    connector = LocalFilesConnector(config)
    request = authorized_request(
        connector, "local-files.discover", "discover", ("root-one",)
    )
    first = connector.discover(request)
    assert first.checkpoint is not None
    original = LocalFilesConnector._candidate
    visited: list[str] = []

    def observed(self, path, approved_root, run_id, root_path, root_device):
        visited.append(path.name)
        return original(self, path, approved_root, run_id, root_path, root_device)

    monkeypatch.setattr(LocalFilesConnector, "_candidate", observed)
    second = LocalFilesConnector(config).discover(request, first.checkpoint)
    assert visited == ["file-2.txt", "file-3.txt"]
    assert second.processed_resources == 4
    checkpoint = second.checkpoint
    while checkpoint is not None:
        result = LocalFilesConnector(config).discover(request, checkpoint)
        checkpoint = result.checkpoint
    candidates = connector.catalogue.candidates_for_run(request.correlation_id)
    assert len(candidates) == 6
    assert len({item.resource_id for item in candidates}) == 6


def test_configuration_loader_fails_closed_and_rejects_unsafe_roots(
    tmp_path: Path,
) -> None:
    root = (tmp_path / "root").resolve()
    root.mkdir()
    payload = {
        "schema_version": "1.0.0",
        "roots": [
            {
                "root_id": "root-one",
                "path": str(root),
                "security_domain": SecurityDomain(
                    "TEST", "Test", "tenant-test"
                ).to_dict(),
                "classification": Classification(
                    "scheme", "internal", "Internal"
                ).to_dict(),
            }
        ],
        "catalogue_path": str((tmp_path / "protected" / "catalogue.db").resolve()),
        "content_store_path": str((tmp_path / "protected" / "content").resolve()),
        "job_store_path": str((tmp_path / "protected" / "jobs.db").resolve()),
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_config(path).roots[0].root_id == "root-one"
    payload["unknown"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        load_config(path)
    payload.pop("unknown")
    payload["roots"][0]["path"] = "relative"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="absolute"):
        load_config(path)

    payload["roots"][0]["path"] = str(root)
    payload["catalogue_path"] = str(
        (tmp_path / "repository" / "catalogue.db").resolve()
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="outside the repository"):
        load_config(path, repository_root=(tmp_path / "repository").resolve())


def test_filesystem_root_and_unsafe_symlink_mode_are_rejected(tmp_path: Path) -> None:
    domain = SecurityDomain("TEST", "Test", "tenant-test")
    classification = Classification("scheme", "internal", "Internal")
    with pytest.raises(ValueError, match="too broad"):
        ApprovedRoot("too-broad", Path("/"), domain, classification)
    root = (tmp_path / "root").resolve()
    root.mkdir()
    with pytest.raises(ValueError, match="same-filesystem"):
        LocalFilesConfig(
            (ApprovedRoot("root-one", root, domain, classification),),
            (tmp_path / "catalogue.db").resolve(),
            (tmp_path / "content").resolve(),
            symlink_policy=SymlinkPolicy.WITHIN_ROOT,
            stay_on_filesystem=False,
        )


def test_overlapping_roots_are_rejected_across_domains(tmp_path: Path) -> None:
    root = (tmp_path / "root").resolve()
    child = root / "child"
    child.mkdir(parents=True)
    classification = Classification("scheme", "internal", "Internal")
    with pytest.raises(ValueError, match="must not overlap"):
        LocalFilesConfig(
            (
                ApprovedRoot(
                    "one",
                    root,
                    SecurityDomain("ONE", "One", "tenant-test"),
                    classification,
                ),
                ApprovedRoot(
                    "two",
                    child,
                    SecurityDomain("TWO", "Two", "tenant-test"),
                    classification,
                ),
            ),
            (tmp_path / "catalogue.db").resolve(),
            (tmp_path / "content").resolve(),
        )


def test_cli_discovery_cannot_bypass_denied_policy(tmp_path: Path) -> None:
    root = (tmp_path / "root").resolve()
    root.mkdir()
    (root / "private.txt").write_text("must not be read", encoding="utf-8")
    domain = SecurityDomain("TEST", "Test", "tenant-test")
    classification = Classification("scheme", "internal", "Internal")
    config_path = tmp_path / "config.json"
    catalogue_path = (tmp_path / "protected" / "catalogue.db").resolve()
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "roots": [
                    {
                        "root_id": "root-one",
                        "path": str(root),
                        "security_domain": domain.to_dict(),
                        "classification": classification.to_dict(),
                    }
                ],
                "catalogue_path": str(catalogue_path),
                "content_store_path": str(
                    (tmp_path / "protected" / "content").resolve()
                ),
                "job_store_path": str((tmp_path / "protected" / "jobs.db").resolve()),
            }
        ),
        encoding="utf-8",
    )
    principal = PrincipalContext(
        "principal-one", "tenant-test", frozenset({domain}), True
    )
    policy = PolicySet(
        "deny-local-files",
        "1.0.0",
        (
            PolicyRule(
                "deny:discover",
                PermissionOutcome.PROHIBITED,
                "Synthetic denial.",
                tenant_ids=frozenset({"tenant-test"}),
                domain_ids=frozenset({"TEST"}),
                capability_ids=frozenset({"local-files.discover"}),
                operations=frozenset({"discover"}),
            ),
        ),
    )
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "principal": principal.to_dict(),
                "purpose": Purpose("local-files-test", "Synthetic test").to_dict(),
                "policy_set": policy.to_dict(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as error:
        local_files_main(
            [
                "discover",
                "--config",
                str(config_path),
                "--authority",
                str(authority_path),
                "--root-id",
                "root-one",
                "--run-next",
            ]
        )
    assert error.value.code == 2
    with sqlite3.connect(catalogue_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM discovery_runs").fetchone()[0] == 0
        )
