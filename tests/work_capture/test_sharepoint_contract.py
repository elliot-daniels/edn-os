from __future__ import annotations

import json
from pathlib import Path

CONTRACT = (
    Path(__file__).parents[2] / "config" / "work-capture-v1-sharepoint-contract.json"
)
RECEIPT = (
    Path(__file__).parents[2] / "config" / "work-capture-v1-activation-receipt.json"
)

CREATED_FIELDS = {
    "WorkCaptureID",
    "WorkCaptureSubmissionKey",
    "WorkCaptureSchemaVersion",
    "WorkCaptureProjectID",
    "WorkCaptureClientID",
    "Engineer",
    "DurationMinutes",
    "WorkSummary",
    "OutcomeStatus",
    "BillingTreatment",
    "FollowUpRequired",
    "FollowUpSummary",
    "FollowUpDue",
    "EvidenceRequirementApplied",
    "EvidenceStatus",
    "EvidenceReferencesJson",
    "SecureSiteApplied",
    "PhotoPolicyApplied",
    "PhotoAuthorizationRef",
    "CaptureMethod",
    "SourceAppVersion",
    "CapturedAt",
    "ProjectProfileVersion",
    "FactOrigin",
    "DefaultedFieldsJson",
    "WorkCaptureRevision",
    "SupersedesWorkCaptureID",
    "CorrectionReason",
    "WorkCapturePayloadHash",
}

DORMANT_FIELDS = {
    "WorkStartedAt",
    "RateClass",
    "BillingCode",
    "TechnicalValue",
    "TechnicalNote",
}


def _contract() -> dict[str, object]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_contract_binds_proven_site_and_work_log_identifiers() -> None:
    value = _contract()
    canonical = value["canonical_owner"]
    profile = value["project_profile"]
    clients = value["clients"]
    site = value["site"]
    assert isinstance(canonical, dict)
    assert isinstance(profile, dict)
    assert isinstance(clients, dict)
    assert isinstance(site, dict)

    assert canonical["logical_name"] == "Work Log"
    assert canonical["existing_structure_required"] is True
    assert canonical["list_id"] == "7b6d10ec-c009-422a-9802-c907d3d4f57f"
    assert profile["logical_name"] == "Projects"
    assert profile["list_id"] == "66944251-b9a3-40cc-9a59-05538e200c19"
    assert clients["list_id"] == "3d55c612-9799-4462-9474-7f0ca5a10b24"
    assert site["site_id"] == "49cc1059-a4f6-42f7-88bd-9940503ae28f"
    assert site["url"] == "https://edn123.sharepoint.com/sites/EDNSystems"
    assert value["status"] == (
        "schema-activated-identifiers-bound-no-live-content-integration"
    )


def test_contract_records_created_field_set_without_claiming_integration() -> None:
    value = _contract()
    live_schema = value["live_schema"]
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert isinstance(live_schema, dict)
    results = receipt["activation_results"]
    assert isinstance(results, dict)

    created = live_schema["created_optional_internal_names"]
    dormant = live_schema["dormant_uncreated_internal_names"]
    assert isinstance(created, list)
    assert isinstance(dormant, list)
    assert set(created) == CREATED_FIELDS
    assert set(dormant) == DORMANT_FIELDS
    assert set(results["work_log_fields_created"]) == CREATED_FIELDS
    assert live_schema["existing_fields_changed"] == []
    assert live_schema["live_content_integration"] is False
    assert live_schema["acceptance_flow_exists"] is False
    assert live_schema["app_submission_path_exists"] is False
    assert live_schema["capture_executed"] is False


def test_contract_stores_evidence_references_not_binary() -> None:
    value = _contract()
    fields = value["field_contract"]
    assert isinstance(fields, list)
    evidence = next(
        item
        for item in fields
        if isinstance(item, dict) and item.get("semantic") == "evidence_references"
    )

    assert evidence["type"] == "NotePlainText"
    assert evidence["binary_content_prohibited"] is True
    assert all(
        not (isinstance(item, dict) and item.get("type") == "Binary")
        for item in fields
    )


def test_contract_declares_every_planned_destination() -> None:
    value = _contract()
    bindings = value["downstream_bindings"]
    assert isinstance(bindings, list)
    destinations = {
        str(item["destination"])
        for item in bindings
        if isinstance(item, dict) and "destination" in item
    }

    assert destinations == {
        "Project activity/history",
        "Actions",
        "Evidence & Test Results",
        "Project Files",
        "Engineering Knowledge",
        "Weekly summary",
        "Billing preparation",
        "Daily Intelligence",
    }
    physical = {
        str(item["destination"]): item.get("list_id")
        for item in bindings
        if isinstance(item, dict) and item.get("existing_structure")
    }
    derived = [
        item
        for item in bindings
        if isinstance(item, dict) and item.get("mode") in {
            "derived-view",
            "authorised-read-reference",
        }
    ]
    assert physical["Project activity/history"] == (
        "66944251-b9a3-40cc-9a59-05538e200c19"
    )
    assert physical["Actions"] == "d7079aad-7f18-4164-8bd6-41f5629898bb"
    assert physical["Evidence & Test Results"] == (
        "0febf366-e8c8-4f43-ad33-26123fb9957d"
    )
    assert physical["Project Files"] == "3363639a-c52d-4789-b2cf-34a71ef9a793"
    assert physical["Engineering Knowledge"] == (
        "adb9a65b-2429-4528-b9c3-04dae9d2cfc0"
    )
    assert all(item.get("list_id") is None for item in derived)
    assert all(
        item.get("content_integration") is False
        for item in bindings
        if isinstance(item, dict)
    )
