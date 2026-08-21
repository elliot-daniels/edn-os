from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "config" / "work-capture-v1-activation-manifest.json"
FLOW_PROPOSAL = ROOT / "config" / "work-capture-v1-flow-activation-proposal.json"
SCRIPT = ROOT / "installer" / "Activate-UWCWorkLogSchema.ps1"
PACK = ROOT / "docs" / "work-capture" / "MANUAL-MAKER-ACTIVATION-PACK.md"
STUDIO = ROOT / "docs" / "work-capture" / "POWER-APPS-STUDIO-V1-RUNBOOK.md"
URL_TEST = ROOT / "tests" / "work_capture" / "Test-Activate-UWCWorkLogSchemaUrl.ps1"
CHOICE_TEST = (
    ROOT / "tests" / "work_capture" / "Test-Activate-UWCWorkLogSchemaChoices.ps1"
)
WEBHOOK_TEST = (
    ROOT / "tests" / "work_capture" / "Test-Activate-UWCWorkLogSchemaWebhooks.ps1"
)
EXPECTED_HASH = "ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca"

EXPECTED_FIELDS = {
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


def test_schema_script_is_exactly_manifest_bound_and_non_executed() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    actual_hash = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()

    assert actual_hash == EXPECTED_HASH
    assert EXPECTED_HASH in script
    assert "https://edn123.sharepoint.com/sites/EDNSystems" in script
    assert "7b6d10ec-c009-422a-9802-c907d3d4f57f" in script
    assert "3c063b23-b83b-401b-9697-bf281c0d71b8" in script
    assert "Connect-PnPOnline" in script
    assert "-Interactive" in script
    assert "-ReturnConnection" in script

    internal_names = re.findall(r'InternalName = "([A-Za-z0-9]+)"', script)
    assert len(internal_names) == len(EXPECTED_FIELDS)
    assert set(internal_names) == EXPECTED_FIELDS

    for prohibited in (
        "Remove-PnP",
        "Set-PnPField",
        "Set-PnPView",
        "Add-PnPWebhook",
        "Remove-PnPWebhook",
        "Set-PnPListItem",
        "Remove-PnPListItem",
    ):
        assert prohibited not in script


def test_schema_script_preflights_and_preserves_existing_dependencies() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    for existing in (
        "ProjectLookup",
        "ClientLookup",
        "ActionLookup",
        "WorkDate",
        "Hours",
        "WorkType",
        "TechnicalSummary",
        "Billable",
        "RateCode",
        "TaskReference",
        "Project",
        "Client",
    ):
        assert f'Assert-ExistingField $fieldMap "{existing}"' in script

    assert '"APEX-95", "Scheduled Night-135"' in script
    assert "Get-PnPView" in script
    assert "Get-PnPWebhookSubscription" in script
    assert "Get-ExistingSchemaSnapshot" in script
    assert "beforeSnapshot.Hash -cne $afterSnapshot.Hash" in script
    assert "Add-PnPFieldFromXml" in script
    assert "ShouldProcess" in script


def test_schema_script_accepts_only_equivalent_case_insensitive_site_urls() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    regression = URL_TEST.read_text(encoding="utf-8")

    assert "Test-EquivalentSharePointSiteUrl" in script
    assert "[Uri]::TryCreate" in script
    assert "[StringComparer]::OrdinalIgnoreCase" in script
    assert ".IdnHost" in script
    assert ".AbsolutePath" in script
    assert '$connection.Url.TrimEnd("/") -cne $siteUrl' not in script

    assert "https://edn123.sharepoint.com/sites/EDNSystems" in regression
    assert "https://edn123.sharepoint.com/sites/ednsystems" in regression
    assert "https://edn123.sharepoint.com/sites/AnotherSite" in regression


def test_schema_script_loads_choices_from_supported_schema_xml() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    regression = CHOICE_TEST.read_text(encoding="utf-8")

    includes_match = re.search(r"\$fieldIncludes = @\((.*?)\n\)", script, re.DOTALL)
    assert includes_match is not None
    includes = includes_match.group(1)
    assert '"SchemaXml"' in includes
    assert '"Choices"' not in includes
    assert '"LookupList"' not in includes
    assert '"LookupField"' not in includes

    assert "Get-UwcChoiceValuesFromSchema" in script
    assert "Get-UwcLookupIdentityFromSchema" in script
    assert "$actualChoices -cnotcontains $choice" in script
    assert "exposes no CHOICE values" in script
    assert "APEX-95" in regression
    assert "Scheduled Night-135" in regression
    assert "Missing required choice validation was bypassed" in regression
    assert "Empty choice-schema validation was bypassed" in regression


def test_schema_script_accepts_empty_webhooks_and_keeps_metadata_only() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    regression = WEBHOOK_TEST.read_text(encoding="utf-8")

    assert "Get-UwcWebhookMetadataSnapshot" in script
    assert "[AllowEmptyCollection()]" in script
    assert "ExpirationUtc" in script
    assert "NotificationUrl" not in script
    assert "ClientState" not in script
    assert "Webhook collection contains a null entry" in script
    assert "Webhook collection contains duplicate identity" in script
    assert "-Webhooks @()" in regression
    assert "Well-formed webhooks were not retained" in regression
    assert "Malformed webhook validation was bypassed" in regression
    assert "Ambiguous webhook validation was bypassed" in regression


def test_manual_flow_contract_is_standard_only_and_exact() -> None:
    pack = PACK.read_text(encoding="utf-8")

    assert "Power Apps (V2)" in pack
    assert "Provided by run-only user" in pack
    assert "submissionKey" in pack
    assert "payloadJson" in pack
    assert "UWC-AcceptCapture-v1" in pack
    for output in (
        "status",
        "captureId",
        "workLogItemId",
        "workLogItemUrl",
        "evidenceStatus",
        "message",
    ):
        assert f"`{output}`" in pack

    assert "same key/same facts" in pack
    assert "same key/different facts" in pack
    assert "WorkCapturePayloadHash" in pack
    assert "leaves it blank" in pack
    assert "Base64 is encoding, not hashing" in pack
    assert "does not use Dataverse" in pack
    assert "premium" in pack
    assert "connector" in pack
    assert "no Action is expected" in pack

    schema_match = re.search(
        r"Use this exact schema:\n\n```json\n(.*?)\n```",
        pack,
        flags=re.DOTALL,
    )
    assert schema_match is not None
    payload_schema = json.loads(schema_match.group(1))
    assert set(payload_schema["required"]) == set(payload_schema["properties"])
    assert "capturedAtClient" not in payload_schema["properties"]


def test_studio_contract_matches_manual_flow() -> None:
    studio = STUDIO.read_text(encoding="utf-8")

    assert 'captureMethod: "mobile_app"' in studio
    assert "projectProfileModified: varSelectedProject.Modified" in studio
    assert "varAttemptSubmissionKey" in studio
    assert "varAttemptPayloadJson" in studio
    assert "varLastSubmissionKey" in studio
    assert "varLastPayloadJson" in studio
    assert "DisplayMode.Disabled" in studio
    assert "varAttemptSubmissionKey,\n            varAttemptPayloadJson" in studio
    assert "uwcConflictTest" in studio
    assert "Actions or Project Files projections" in studio
    assert 'captureMethod: "power_apps"' not in studio
    assert "projectProfileVersion:" not in studio


def test_flow_stage_is_separately_authorised_and_not_executed() -> None:
    proposal = json.loads(FLOW_PROPOSAL.read_text(encoding="utf-8"))

    assert proposal["status"] == "authorised-awaiting-window-not-executed"
    assert proposal["separate_from_schema_authority"] is True
    assert proposal["binding"]["manifest_sha256"] == EXPECTED_HASH
    assert proposal["binding"]["schema_result_commit"] == (
        "e0df0aebd0b4b9bd7b362f6f46aa9f7872d363a7"
    )
    assert proposal["target"]["flow_name"] == "UWC-AcceptCapture-v1"
    assert proposal["authority"]["received"] is True
    assert proposal["authority"]["execution_status"] == "not-started-awaiting-window"
    assert proposal["completed_dependency"]["work_log_fields_created"] == 29
    assert proposal["completed_dependency"]["idempotency_rerun_created"] == 0
    assert "do not run the flow or create a Work Log item" in proposal[
        "stage_stop_boundary"
    ]
    assert proposal["exact_owner_go"].startswith("GO — approve")
