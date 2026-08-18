from __future__ import annotations

import json
from pathlib import Path

CONTRACT = (
    Path(__file__).parents[2] / "config" / "work-capture-v1-sharepoint-contract.json"
)


def _contract() -> dict[str, object]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_contract_reuses_work_log_and_remains_unbound() -> None:
    value = _contract()
    canonical = value["canonical_owner"]
    profile = value["project_profile"]
    assert isinstance(canonical, dict)
    assert isinstance(profile, dict)

    assert canonical["logical_name"] == "Work Log"
    assert canonical["existing_structure_required"] is True
    assert canonical["list_id"] is None
    assert profile["logical_name"] == "Projects"
    assert profile["list_id"] is None
    assert value["status"] == "design-only-unbound-no-live-mutation-authorised"


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
    assert all(
        item.get("list_id") is None for item in bindings if isinstance(item, dict)
    )
