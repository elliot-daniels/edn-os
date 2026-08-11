"""Minimal fail-closed operator CLI for Local Files metadata discovery."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from edn.connectors.local_files import LocalFilesConnector, load_config
from edn.core import (
    CapabilityRegistry,
    CapabilityUseDecision,
    Classification,
    PermissionEvaluator,
    PermissionRequest,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    evaluate_capability_use,
)
from edn.jobs import (
    Job,
    JobProgress,
    JobService,
    JobStatus,
    JobStore,
    JobType,
    LocalJobWorker,
    RetryPolicy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-files")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-config", "capabilities"):
        command = subcommands.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
    for name in ("discover-plan", "discover"):
        command = subcommands.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
        command.add_argument("--authority", required=True, type=Path)
        command.add_argument("--root-id", required=True)
    discover = subcommands.choices["discover"]
    discover.add_argument("--job-id")
    discover.add_argument("--run-next", action="store_true")
    summary = subcommands.add_parser("summary")
    summary.add_argument("--config", required=True, type=Path)
    summary.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config, repository_root=_repository_root())
        if args.command == "validate-config":
            _print(
                {
                    "status": "valid",
                    "schema_version": config.schema_version,
                    "configuration_hash": config.configuration_hash,
                }
            )
            return 0
        connector = LocalFilesConnector(config)
        if args.command == "capabilities":
            _print(
                {
                    "capabilities": [
                        item.to_dict() for item in connector.manifest.capabilities
                    ]
                }
            )
            return 0
        if args.command == "summary":
            _print(_summary(connector, args.run_id))
            return 0
        principal, purpose, evaluator = _load_authority(args.authority)
        root = config.root(args.root_id)
        registry = _registry(connector)
        decision = _decision(
            registry,
            evaluator,
            principal,
            purpose,
            root.security_domain,
            root.classification,
            (root.root_id,),
        )
        if args.command == "discover-plan":
            _print(
                {
                    "mode": "PLAN",
                    "operation": "READ-ONLY DISCOVERY",
                    "content_ingestion": False,
                    "root_ids": [root.root_id],
                    "configuration_hash": config.configuration_hash,
                    "authority": decision.to_dict(),
                }
            )
            return 0 if decision.is_usable else 2
        if not decision.is_usable:
            raise PermissionError(f"discovery authority denied: {decision.reason_code}")
        if config.job_store_path is None:
            raise ValueError("discover requires job_store_path in configuration")
        now = datetime.now(UTC)
        job_id = args.job_id or f"local-files:{uuid4().hex}"
        store = JobStore(config.job_store_path)
        store.initialise()
        existing = store.get(job_id)
        if existing is None:
            job = Job(
                job_id,
                JobType.DISCOVERY,
                connector.manifest.connector_id,
                connector.manifest.version,
                config.configuration_hash,
                "local-files.discover",
                "discover",
                principal,
                purpose,
                root.security_domain,
                root.classification,
                (root.root_id,),
                f"run:{uuid4().hex}",
                now,
                now,
                JobStatus.READY,
                RetryPolicy(),
                JobProgress("ready"),
            )
            JobService(store).create(job, actor_id=principal.principal_id)
        else:
            job = existing
            if (
                job.configuration_hash != config.configuration_hash
                or job.principal != principal
                or job.purpose != purpose
                or job.resource_scope != (root.root_id,)
                or job.operation != "discover"
            ):
                raise ValueError(
                    "existing job does not match configuration and authority"
                )
        result = job
        if args.run_next:
            worker = LocalJobWorker(
                store,
                registry,
                evaluator,
                (connector,),
                worker_id="local-files-cli",
                configuration_hashes={
                    connector.manifest.connector_id: config.configuration_hash
                },
            )
            result = worker.run_next(now=datetime.now(UTC)) or job
        _print(
            {
                "mode": "READ-ONLY DISCOVERY",
                "content_ingestion": False,
                "job_id": result.job_id,
                "run_id": result.correlation_id,
                "status": result.status.value,
                "processed_items": result.progress.processed_items,
            }
        )
        return 0
    except (KeyError, OSError, PermissionError, RuntimeError, ValueError) as error:
        parser.exit(2, f"local-files: {error}\n")


def _load_authority(
    path: Path,
) -> tuple[PrincipalContext, Purpose, PermissionEvaluator]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("authority file could not be read as JSON") from error
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "principal",
        "purpose",
        "policy_set",
    }:
        raise ValueError("authority file shape is invalid")
    if value.get("schema_version") != "1.0.0":
        raise ValueError("authority schema version is unsupported")
    return (
        PrincipalContext.from_dict(_object(value["principal"])),
        Purpose.from_dict(_object(value["purpose"])),
        PermissionEvaluator(PolicySet.from_dict(_object(value["policy_set"]))),
    )


def _decision(
    registry: CapabilityRegistry,
    evaluator: PermissionEvaluator,
    principal: PrincipalContext,
    purpose: Purpose,
    domain: SecurityDomain,
    classification: Classification,
    scope: tuple[str, ...],
) -> CapabilityUseDecision:
    request = PermissionRequest(
        f"cli:{uuid4().hex}",
        principal,
        purpose,
        "local-files.discover",
        "discover",
        domain,
        classification,
        scope,
    )
    return evaluate_capability_use(registry, evaluator, request, now=datetime.now(UTC))


def _registry(connector: LocalFilesConnector) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    for manifest, runtime in connector.runtime_states():
        registry.register(manifest, runtime)
    return registry


def _summary(connector: LocalFilesConnector, run_id: str) -> dict[str, Any]:
    summary = connector.catalogue.summary(run_id)
    return {
        "run_id": summary.run_id,
        "files_discovered": summary.files_discovered,
        "total_size_bytes": summary.total_size_bytes,
        "categories": dict(summary.category_counts),
        "extensions": dict(summary.extension_counts),
        "age_distribution": dict(summary.age_counts),
        "already_known": summary.already_known,
        "currently_ingestible": summary.potentially_ingestible,
        "unsupported": summary.unsupported,
        "excluded": summary.excluded,
        "warnings": summary.warnings,
        "capability_opportunities": [
            {
                "category": item.category,
                "file_count": item.file_count,
                "total_size_bytes": item.total_size_bytes,
                "missing_capability": item.missing_capability,
            }
            for item in summary.unsupported_capabilities
        ],
        "coverage_opportunities": [
            {
                "coverage_rank": item.coverage_rank,
                "category": item.category,
                "status": item.status.value,
                "records": item.record_count,
                "record_percentage": item.record_percentage,
                "bytes": item.total_size_bytes,
                "byte_percentage": item.byte_percentage,
                "extensions": dict(item.extension_counts),
                "extension_diversity": item.extension_diversity,
                "recency_distribution": dict(item.recency_counts),
                "existing_capability": item.existing_capability,
                "missing_capability": item.missing_capability,
                "security_domains": list(item.security_domains),
                "classifications": list(item.classifications),
                "deterministic_confidence": item.deterministic_confidence,
                "limitations": list(item.limitations),
            }
            for item in summary.coverage_opportunities
        ],
    }


def _repository_root() -> Path | None:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "pyproject.toml").exists() and (
            candidate / "src" / "edn"
        ).exists():
            return candidate
    return None


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("authority nested value must be an object")
    return value


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
