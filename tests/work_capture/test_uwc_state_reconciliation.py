from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
STATE = ROOT / "config" / "work-capture-development-state.json"
AUDIT = ROOT / "config" / "work-capture-development-audit.jsonl"
MANIFEST = ROOT / "config" / "work-capture-v1-activation-manifest.json"
RECEIPT = ROOT / "config" / "work-capture-v1-activation-receipt.json"
CONTRACT = ROOT / "config" / "work-capture-v1-sharepoint-contract.json"
PROPOSAL = ROOT / "config" / "work-capture-v1-flow-activation-proposal.json"
EXPECTED_HASH = "ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca"
HISTORICAL_FLOW_AUTHORITY_EVENT = (
    "work-capture-event:uwc-001-flow-creation-authority-20260821-2005"
)
HISTORICAL_SCHEMA_EVENT = (
    "work-capture-event:uwc-001-schema-activation-completed-20260821"
)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _audit_events() -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in AUDIT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        assert isinstance(event, dict)
        events.append(event)
    return events


def test_frozen_activation_manifest_hash_and_wording_are_preserved() -> None:
    actual = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    sidecar = (
        ROOT / "config" / "work-capture-v1-activation-manifest.sha256"
    ).read_text(encoding="utf-8")
    manifest = _load_json(MANIFEST)
    state = _load_json(STATE)
    freeze = state["activation_manifest_freeze"]
    assert isinstance(freeze, dict)

    assert actual == EXPECTED_HASH
    assert sidecar.startswith(EXPECTED_HASH)
    assert manifest["status"] == "prepared-not-approved-not-executed"
    assert freeze["frozen_sha256"] == EXPECTED_HASH
    assert freeze["frozen_status_field"] == "prepared-not-approved-not-executed"


def test_current_state_records_expired_non_reusable_flow_window() -> None:
    state = _load_json(STATE)
    proposal = _load_json(PROPOSAL)
    receipt = _load_json(RECEIPT)
    authority = state["flow_creation_authority"]
    reconciliation = state["state_reconciliation"]
    assert isinstance(authority, dict)
    assert isinstance(reconciliation, dict)

    assert state["status"] == "schema-completed-flow-window-expired-not-executed"
    assert state["live_microsoft_mutation_authorised"] is False
    assert state["branch"] == "feature/uwc-state-reconciliation"
    assert authority["execution_status"] == "expired-not-executed-non-reusable"
    assert authority["reusable"] is False
    assert authority["flow_created"] is False
    assert proposal["status"] == "expired-not-executed-non-reusable"
    assert proposal["reusable"] is False
    flow_window = receipt["flow_window_reconciliation"]
    assert isinstance(flow_window, dict)
    assert flow_window["reusable"] is False
    assert flow_window["flow_created"] is False
    assert reconciliation["flow_window"] == "expired-not-executed-non-reusable"
    assert reconciliation["main_unmodified"] is True


def test_current_state_does_not_claim_flow_app_capture_or_content_integration() -> None:
    state = _load_json(STATE)
    contract = _load_json(CONTRACT)
    receipt = _load_json(RECEIPT)
    reconciliation = state["state_reconciliation"]
    live_schema = contract["live_schema"]
    results = receipt["activation_results"]
    assert isinstance(reconciliation, dict)
    assert isinstance(live_schema, dict)
    assert isinstance(results, dict)

    for value in (
        reconciliation["live_content_integration"],
        reconciliation["acceptance_flow_exists"],
        reconciliation["app_submission_path_exists"],
        reconciliation["capture_executed"],
        live_schema["live_content_integration"],
        live_schema["acceptance_flow_exists"],
        live_schema["app_submission_path_exists"],
        live_schema["capture_executed"],
    ):
        assert value is False
    assert results["flows_created"] == []
    assert results["sharepoint_records_created"] == []
    assert results["project_files_created"] == []
    assert results["customer_data_used"] is False


def test_historical_audit_events_are_preserved_and_expiry_is_appended() -> None:
    events = _audit_events()
    ids = [str(event["event_id"]) for event in events]
    assert HISTORICAL_SCHEMA_EVENT in ids
    assert HISTORICAL_FLOW_AUTHORITY_EVENT in ids
    assert ids.index(HISTORICAL_SCHEMA_EVENT) < ids.index(
        HISTORICAL_FLOW_AUTHORITY_EVENT
    )
    assert "work-capture-event:uwc-001-flow-window-expired-20260828" in ids
    assert "work-capture-event:uwc-001-state-reconciliation-20260828" in ids

    schema_event = next(
        event for event in events if event["event_id"] == HISTORICAL_SCHEMA_EVENT
    )
    metadata = schema_event["metadata"]
    assert isinstance(metadata, dict)
    first_run = metadata["first_run"]
    assert isinstance(first_run, dict)
    assert first_run["created"] == 29
    expiry = next(
        event
        for event in events
        if event["event_id"]
        == "work-capture-event:uwc-001-flow-window-expired-20260828"
    )
    expiry_metadata = expiry["metadata"]
    assert isinstance(expiry_metadata, dict)
    assert expiry_metadata["reusable"] is False
    assert expiry_metadata["flow_created"] is False
    assert expiry["reason_code"] == (
        "exact_owner_flow_window_ended_without_execution_and_is_not_reusable"
    )
