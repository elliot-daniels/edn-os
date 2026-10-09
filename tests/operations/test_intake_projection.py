"""Pure expected-schema checks; no protected storage or live transport."""

import json

import pytest

from edn.operations import intake_projection as projection


def fixture():
    return json.loads(projection.FIXTURE.read_text(encoding="utf-8"))


def fields():
    return {
        "Title": "Pending",
        "ContactName": "Synthetic Operator",
        "Company": "Example",
        "Email": "operator@example.invalid",
        "Phone": "+61400000000",
        "Site_x002f_Location": "Synthetic site",
        "ServiceRequired": "Site assessment",
        "Urgency": "Routine",
        "JobDescription": "Synthetic request",
        "CustomerReference": "DEMO",
        "Source": "EDN OS Manual",
        "SubmittedAt": "2026-10-08T00:00:00Z",
        "ContractVersion": "1.0",
        "Status": "New",
    }


def test_expected_mapping_and_optional_date():
    mapped = fields()
    assert projection.validate_fields_for_target(mapped, fixture()) == ()
    mapped["PreferredDate"] = "2026-10-09"
    assert projection.validate_fields_for_target(mapped, fixture()) == ()


@pytest.mark.parametrize(
    "name,value",
    [
        ("Title", "x" * 41),
        ("ContactName", "\U0001f600" * 51),
        ("Urgency", "invented"),
        ("PreferredDate", "2026-02-30"),
        ("SubmittedAt", "2026-10-08T00:00:00+10:00"),
        ("Company", "unsafe\nline"),
        ("DurationMinutes", "10"),
    ],
)
def test_incompatible_payload_is_rejected(name, value):
    mapped = fields()
    mapped[name] = value
    assert projection.validate_fields_for_target(mapped, fixture())


def test_unknown_field_diagnostics_do_not_echo_untrusted_names():
    mapped = fields()
    mapped["PRIVATE-CUSTOMER-SECRET"] = "private"
    findings = projection.validate_fields_for_target(mapped, fixture())
    assert findings == ("Unsupported target field supplied",)


def test_fixture_change_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "expected.json"
    changed = fixture()
    changed["columns"]["Title"]["capacity"] = 100
    path.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(projection, "FIXTURE", path)
    with pytest.raises(ValueError, match="pinned fixture"):
        projection.prepare_envelope({"fields": fields()}, ())


def test_dry_run_cannot_claim_success():
    with pytest.raises(ValueError, match="unconfirmed"):
        projection.prepare_envelope(
            {"fields": fields(), "dry_run": True, "sync_status": "synced"}, ()
        )


def approved_payload():
    return {
        "fields": fields(),
        "dry_run": True,
        "sync_status": "dry_run",
        "request_id": "d411af59-c600-413b-a916-a462c395f108",
        "revision": 2,
        "content_hash": "a" * 64,
        "idempotency_key": "synthetic-submission-01",
        "attachment_manifest": (),
        "operation": "create_proposal",
        "not_ready": [
            "Live target identifiers are not configured",
            "Current source permissions are unverified",
        ],
        "target": {
            "integration": "sharepoint",
            "list_contract": "Job Requests",
            "live_status": "unverified",
        },
        "approval": {
            "revision": 2,
            "content_hash": "a" * 64,
            "actor": "local operator (self-approval), uid=1000",
            "timestamp": "2026-10-09T00:00:00Z",
        },
    }


def test_ready_expected_mapping_is_explicitly_not_live_ready():
    result = projection.prepare_envelope(approved_payload(), ())
    assert result["not_synced"] is True
    assert result["schema_validation"]["live_schema_status"] == "unverified"
    assert result["target"] == approved_payload()["target"]
    assert len(result["not_ready"]) == 5
    assert "Current source permissions are unverified" in result["not_ready"]
    assert result["fields"] == fields()


@pytest.mark.parametrize(
    "key,value",
    [
        ("revision", True),
        ("content_hash", "invalid"),
        ("idempotency_key", "hidden\nkey"),
        ("request_id", "invalid"),
        ("approval", {"revision": 1, "content_hash": "a" * 64}),
        ("attachment_manifest", [{"request_id": "different"}]),
    ],
)
def test_incomplete_or_mismatched_approval_never_produces_ready_envelope(key, value):
    payload = approved_payload()
    payload[key] = value
    with pytest.raises(ValueError, match="incomplete or inconsistent"):
        projection.prepare_envelope(payload, ())


def test_website_record_cannot_propose_another_create():
    payload = approved_payload()
    payload["fields"]["Source"] = "EDN Systems Website"
    with pytest.raises(ValueError, match="incomplete or inconsistent"):
        projection.prepare_envelope(payload, ())
    payload["operation"] = "reference_existing"
    identity = {
        "source_system": "sharepoint",
        "source_account": "synthetic-account",
        "site_id": "synthetic-site",
        "list_id": "synthetic-list",
        "native_item_id": "SYNTHETIC-ITEM-01",
    }
    payload["target"].update(identity)
    payload["source_provenance"] = {**identity, "synthetic_only": True}
    ready = projection.prepare_envelope(payload, ())
    assert ready["operation"] == "reference_existing"
    assert ready["target"]["native_item_id"] == "SYNTHETIC-ITEM-01"
