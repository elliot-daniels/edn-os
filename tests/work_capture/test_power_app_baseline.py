from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "config" / "work-capture-power-app-baseline.json"
ACTIVATION_MANIFEST = ROOT / "config" / "work-capture-v1-activation-manifest.json"
ACTIVATION_RECEIPT = ROOT / "config" / "work-capture-v1-activation-receipt.json"
STUDIO_RUNBOOK = ROOT / "docs" / "work-capture" / "POWER-APPS-STUDIO-V1-RUNBOOK.md"
SOURCE = ROOT / "power-platform" / "work-capture" / "canvas" / "EDNWorkCapture" / "Src"


def _manifest() -> dict[str, object]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_baseline_binds_the_exact_unshared_test_app() -> None:
    value = _manifest()
    app = value["app"]
    safety = value["safety"]
    assert isinstance(app, dict)
    assert isinstance(safety, dict)

    assert app["display_name"] == "EDN Work Capture"
    assert app["app_id"] == "a47efc3e-0b52-405a-a220-54930a4ffdc9"
    assert app["environment_id"] == "Default-aae6ab79-45eb-4829-a04f-595becdb936d"
    assert app["shared_users"] == 0
    assert app["shared_groups"] == 0
    assert safety["external_mutations"] == 0
    assert safety["sharepoint_item_reads"] == 0
    assert safety["customer_data_used"] is False


def test_only_supported_generated_canvas_source_is_retained() -> None:
    value = _manifest()
    source_control = value["source_control"]
    assert isinstance(source_control, dict)
    hashes = source_control["files"]
    assert isinstance(hashes, dict)

    assert {path.name for path in SOURCE.iterdir()} == set(hashes)
    for name, expected_hash in hashes.items():
        path = SOURCE / str(name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_hash


def test_source_preserves_canonical_bindings_and_exposes_scaffold_gaps() -> None:
    source = (SOURCE / "Screen1.pa.yaml").read_text(encoding="utf-8")

    assert "DataSource: ='Work Log'" in source
    assert "DefaultMode: =FormMode.New" in source
    assert 'DataField: ="ProjectLookup"' in source
    assert 'DataField: ="ClientLookup"' in source
    assert 'DataField: ="TechnicalSummary"' in source
    assert "Default: =Today()" in source
    assert source.count('Text: ="30m"') == 4
    assert "SubmitForm(" not in source
    assert "OutcomeStatus" not in source


def test_deprecated_round_trip_and_live_update_remain_blocked() -> None:
    value = _manifest()
    export = value["export"]
    live_update = value["live_update"]
    assert isinstance(export, dict)
    assert isinstance(live_update, dict)

    assert export["deprecated_pack_unpack_used"] is False
    assert export["archive_committed"] is False
    assert live_update["authorised"] is False
    assert live_update["cli_upload_available"] is False
    assert live_update["native_git_integration_available"] is False


def test_activation_receipt_records_completed_idempotent_schema_activation() -> None:
    receipt = json.loads(ACTIVATION_RECEIPT.read_text(encoding="utf-8"))
    authority = receipt["authority"]
    target = receipt["target"]
    results = receipt["activation_results"]
    rollback = receipt["rollback"]

    actual_hash = hashlib.sha256(ACTIVATION_MANIFEST.read_bytes()).hexdigest()
    assert authority["required_manifest_sha256"] == actual_hash
    assert authority["observed_manifest_sha256"] == actual_hash
    assert authority["hash_verified"] is True
    assert target["app_id"] == "a47efc3e-0b52-405a-a220-54930a4ffdc9"
    assert receipt["status"] == (
        "schema-activation-completed-flow-window-expired-not-executed"
    )
    assert receipt["historical_status"] == (
        "schema-activation-completed-flow-stage-not-authorised"
    )
    assert authority["operator"] == "elliot-owner"
    assert authority["window_start"] == "2026-08-21T19:05:00+09:30"
    assert authority["window_end"] == "2026-08-21T20:00:00+09:30"
    assert authority["activation_pack_commit"] == (
        "be42606236f1cebb2e8a03369a43f5a7a75c9a94"
    )
    execution = receipt["current_execution"]
    assert execution["execution_reported"] is True
    assert execution["previous_attempt"]["result"] == "stopped-before-mutation"
    assert execution["prior_attempt"]["result"] == "stopped-before-mutation"
    assert execution["last_attempt"]["result"] == "stopped-before-mutation"
    assert execution["last_attempt"]["sharepoint_mutations"] == 0
    assert execution["site_url_repair_commit"] == (
        "c2cb6640e3aaa8f7bbc9a290ca3deef10c8faad2"
    )
    assert execution["choice_retrieval_repair_commit"] == (
        "b3cacc6d27531e5f5bc0c474ff0b961ded4d9eac"
    )
    assert execution["empty_webhook_repair_commit"] == (
        "07ad09cc0a53a2340f6325936a9b5c90a8284137"
    )
    completed = execution["completed_result"]
    assert completed["first_run"]["created"] == 29
    assert completed["first_run"]["existing_fields_changed"] == 0
    assert completed["idempotency_rerun"]["created"] == 0
    assert completed["idempotency_rerun"]["reused_compatible"] == 29
    assert execution["retry_authorised_within_current_window"] is False
    assert results["external_mutations"] == 29
    assert len(results["work_log_fields_created"]) == 29
    assert "WorkCaptureID" in results["work_log_fields_created"]
    assert "WorkCapturePayloadHash" in results["work_log_fields_created"]
    assert results["work_log_fields_changed"] == []
    assert results["flows_created"] == []
    assert results["customer_data_used"] is False
    assert rollback["required"] is False
    flow_window = receipt["flow_window_reconciliation"]
    assert flow_window["flow_name"] == "UWC-AcceptCapture-v1"
    assert flow_window["execution_status"] == "expired-not-executed"
    assert flow_window["reusable"] is False
    assert flow_window["flow_created"] is False
    assert flow_window["flow_run"] is False
    assert "expired unused and is not reusable" in execution["next_action"]


def test_studio_runbook_uses_existing_controls_and_supported_boundary() -> None:
    runbook = STUDIO_RUNBOOK.read_text(encoding="utf-8")

    for control in (
        "Form2",
        "DataCardValue4",
        "DataCardValue5",
        "DataCardValue6",
        "DataCardValue7",
        "DataCardValue8",
        "DataCardValue9",
        "DataCardValue10",
        "DataCardValue11",
        "Button1",
        "Button1_1",
        "Button1_2",
        "Button1_3",
    ):
        assert f"`{control}`" in runbook

    assert "UWC-AcceptCapture-v1" in runbook
    assert '"15m"' in runbook
    assert '"30m"' in runbook
    assert '"1h"' in runbook
    assert '"2h"' in runbook
    assert '"Other"' in runbook
    assert "pac canvas pack/unpack" in runbook
    assert "Never deploy the generated YAML" in runbook
    assert (
        "https://apps.powerapps.com/play/e/"
        "Default-aae6ab79-45eb-4829-a04f-595becdb936d/a/"
        "a47efc3e-0b52-405a-a220-54930a4ffdc9"
    ) in runbook
