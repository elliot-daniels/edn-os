"""Durable, content-free PA-009 provider lifecycle audit tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edn.intelligence import (
    DurableProviderAudit,
    DurableProviderAuditError,
    ProviderAuditRecord,
)


def _record(*, status: str = "transport_started") -> ProviderAuditRecord:
    outcomes = {
        "dispatch_admitted": "admitted",
        "transport_started": "transport_started",
        "completed": "completed",
    }
    return ProviderAuditRecord(
        timestamp=datetime(2026, 8, 14, tzinfo=UTC),
        request_id="request-durable-1",
        provider_id="openai.api",
        model="gpt-5-mini-2025-08-07",
        disclosure_policy="openai-daily-brief-pilot-v1",
        evidence_item_count=7,
        projected_categories=(
            "calendar.metadata",
            "inbox.metadata",
            "local-files.metadata",
        ),
        projected_payload_size=799,
        classification_ceiling="confidential",
        security_domain="EDN",
        disclosure_decision="allowed",
        dispatch_status=status,
        preflight_hash="a" * 64,
        attempt_number=1,
        transport_attempted=status != "dispatch_admitted",
        final_outcome=outcomes[status],
    )


def test_durable_audit_permissions_atomic_chain_and_separate_process_readback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "provider-audits"
    audit = DurableProviderAudit(root)
    audit.append(_record(status="dispatch_admitted"))
    audit.append(_record(status="transport_started"))
    audit.append(replace(_record(status="completed"), final_outcome="completed"))

    audit_file = next(root.glob("*.json"))
    lock_file = next(root.glob("*.lock"))
    assert oct(root.stat().st_mode & 0o777) == "0o700"
    assert oct(audit_file.stat().st_mode & 0o777) == "0o600"
    assert oct(lock_file.stat().st_mode & 0o777) == "0o600"
    assert audit_file.stat().st_uid == os.geteuid()
    code = (
        "import json,sys; from pathlib import Path; "
        "from edn.intelligence import DurableProviderAudit; "
        "records=DurableProviderAudit(Path(sys.argv[1])).read_lifecycle(sys.argv[2]); "
        "print(json.dumps([r.dispatch_status for r in records]))"
    )
    output = subprocess.check_output(
        [sys.executable, "-c", code, str(root), "request-durable-1"],
        text=True,
    )
    assert json.loads(output) == [
        "dispatch_admitted",
        "transport_started",
        "completed",
    ]


def test_durable_audit_detects_tampering_and_unsafe_paths(tmp_path: Path) -> None:
    root = tmp_path / "provider-audits"
    audit = DurableProviderAudit(root)
    audit.append(_record())
    audit_file = next(root.glob("*.json"))
    payload = json.loads(audit_file.read_text())
    payload["entries"][0]["record"]["dispatch_status"] = "completed"
    audit_file.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    audit_file.chmod(0o600)
    with pytest.raises(DurableProviderAuditError, match="chain"):
        audit.read_lifecycle("request-durable-1")

    unsafe_root = tmp_path / "unsafe"
    unsafe_root.symlink_to(root, target_is_directory=True)
    with pytest.raises(DurableProviderAuditError, match="path type"):
        DurableProviderAudit(unsafe_root).append(_record())


def test_durable_audit_serialization_excludes_content_and_authority() -> None:
    keys = set(_record().to_dict())
    prohibited = {
        "prompt",
        "response",
        "structured_output",
        "statement_text",
        "evidence",
        "projection",
        "credential",
        "authorization",
        "api_key",
        "approval",
        "approval_token",
    }
    assert not keys & prohibited
    with pytest.raises(ValueError, match="ProviderFailureCode"):
        _record().__class__(
            **{
                **_record().to_dict(),
                "timestamp": datetime(2026, 8, 14, tzinfo=UTC),
                "projected_categories": _record().projected_categories,
                "statement_counts": (),
                "failure_reason": "provider generated secret text",
            }
        )
