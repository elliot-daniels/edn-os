"""Pure dry-run validation against pinned expected Job Requests columns."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

FIXTURE = (
    Path(__file__).resolve().parents[3] / "config/work-intake-job-requests-schema.json"
)
EXPECTED_FIXTURE_HASH = (
    "f04013c38be0d4134bbd9d3f1b0f0cf757d79886bc1b8dbfec959182abacf1ae"
)
REQUIRED = frozenset(
    {
        "Title",
        "ContactName",
        "Company",
        "Email",
        "Phone",
        "Site_x002f_Location",
        "ServiceRequired",
        "Urgency",
        "JobDescription",
        "CustomerReference",
        "Source",
        "SubmittedAt",
        "ContractVersion",
        "Status",
    }
)


def validate_fields_for_target(
    fields: dict[str, Any], schema: dict[str, Any]
) -> tuple[str, ...]:
    findings = []
    columns = schema.get("columns")
    if not isinstance(columns, dict):
        return ("Expected schema is unavailable",)
    if not fields.keys() >= REQUIRED:
        findings.append("Required target fields are missing")
    for name, value in fields.items():
        rule = columns.get(name)
        if not isinstance(rule, dict) or not isinstance(value, str):
            findings.append("Unsupported target field supplied")
            continue
        kind = rule.get("type")
        if kind == "text":
            capacity = rule.get("capacity")
            if type(capacity) is not int or capacity < 1:
                findings.append(f"Unknown target capacity: {name}")
            else:
                try:
                    size = len(value.encode("utf-16-le")) // 2
                except UnicodeError:
                    size = capacity + 1
                if size > capacity:
                    findings.append(f"Target capacity exceeded: {name}")
                if not rule.get("multiline") and any(c in value for c in "\r\n\t"):
                    findings.append(f"Target field requires single-line text: {name}")
        elif kind == "choice":
            choices = rule.get("choices")
            if not isinstance(choices, list) or value not in choices:
                findings.append(f"Unsupported target choice: {name}")
        elif kind == "date":
            try:
                if (
                    rule.get("format") != "dateOnly"
                    or date.fromisoformat(value).isoformat() != value
                ):
                    raise ValueError
            except ValueError:
                findings.append(f"Invalid target date: {name}")
        elif kind == "datetime":
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if rule.get(
                    "format"
                ) != "dateTime" or timestamp.utcoffset() != UTC.utcoffset(timestamp):
                    raise ValueError
            except ValueError:
                findings.append(f"Invalid target timestamp: {name}")
        else:
            findings.append(f"Unsupported target type: {name}")
    return tuple(findings)


def prepare_envelope(
    payload: dict[str, Any], evidence: tuple[dict[str, object], ...]
) -> dict[str, Any]:
    with FIXTURE.open("rb") as incoming:
        raw = incoming.read(65537)
    if len(raw) > 65536:
        raise ValueError("Expected target schema exceeds its bound")
    schema = json.loads(raw)
    fingerprint = hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if fingerprint != EXPECTED_FIXTURE_HASH:
        raise ValueError("Expected target schema is not the pinned fixture")
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("Dry-run fields are unavailable")
    findings = validate_fields_for_target(fields, schema)
    if findings:
        raise ValueError("Dry-run target validation failed")
    if payload.get("dry_run") is not True or payload.get("sync_status") != "dry_run":
        raise ValueError("Dry-run status is unconfirmed")
    try:
        request_id = payload["request_id"]
        if not isinstance(request_id, str) or str(UUID(request_id)) != request_id:
            raise ValueError
        revision = payload["revision"]
        content_hash = payload["content_hash"]
        approval = payload["approval"]
        key = payload["idempotency_key"]
        target = payload["target"]
        operation = payload["operation"]
        if (
            type(revision) is not int
            or revision < 1
            or not isinstance(content_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None
            or not isinstance(key, str)
            or not 1 <= len(key) <= 256
            or any(ord(character) < 33 or ord(character) > 126 for character in key)
            or not isinstance(approval, dict)
            or type(approval.get("revision")) is not int
            or approval.get("revision") != revision
            or approval.get("content_hash") != content_hash
            or not isinstance(approval.get("actor"), str)
            or not approval["actor"]
            or not isinstance(approval.get("timestamp"), str)
            or tuple(payload["attachment_manifest"]) != evidence
            or not isinstance(target, dict)
            or target.get("integration") != "sharepoint"
            or target.get("list_contract") != "Job Requests"
            or target.get("live_status") != "unverified"
            or operation not in {"create_proposal", "reference_existing"}
        ):
            raise ValueError
        timestamp = datetime.fromisoformat(approval["timestamp"].replace("Z", "+00:00"))
        if timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise ValueError
        if (
            fields.get("Source") == "EDN Systems Website"
            and operation != "reference_existing"
        ):
            raise ValueError
        if operation == "reference_existing":
            provenance = payload["source_provenance"]
            if (
                not isinstance(provenance, dict)
                or provenance.get("synthetic_only") is not True
            ):
                raise ValueError
            for name in (
                "source_system",
                "source_account",
                "site_id",
                "list_id",
                "native_item_id",
            ):
                value = target.get(name)
                if (
                    not isinstance(value, str)
                    or not value
                    or provenance.get(name) != value
                ):
                    raise ValueError
        total_bytes = 0
        for item in evidence:
            size = item.get("size_bytes")
            if item.get("request_id") != request_id or type(size) is not int:
                raise ValueError
            if not isinstance(size, int) or size <= 0:
                raise ValueError
            total_bytes += size
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError(
            "Approved dry-run evidence is incomplete or inconsistent"
        ) from None
    return {
        **payload,
        "evidence_references": [
            {**item, "location": "local_only", "uploaded": False} for item in evidence
        ],
        "schema_validation": {
            "status": "matches_pinned_expected_schema",
            "live_schema_status": "unverified",
            "source_commit": schema["source_commit"],
            "request_contract_commit": schema["request_contract_commit"],
            "fixture_sha256": fingerprint,
            "findings": [],
        },
        "not_synced": True,
        "target": target,
        "not_ready": [
            "Live SharePoint schema is unverified",
            "Live transport is not authorised or enabled",
            "Attachments are local evidence and have not been uploaded",
        ],
        "attachment_manifest": {
            "request_id": payload["request_id"],
            "revision": payload["revision"],
            "content_hash": payload.get("content_hash"),
            "status": "local_only",
            "files": list(evidence),
            "total_bytes": total_bytes,
        },
    }
