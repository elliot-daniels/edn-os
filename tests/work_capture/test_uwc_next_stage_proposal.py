from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
PROPOSAL = ROOT / "config" / "work-capture-next-stage-proposal.json"


def _proposal() -> dict[str, object]:
    value = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_proposal_is_repository_only_and_requires_fresh_owner_go() -> None:
    value = _proposal()
    authority = value["authority"]
    boundaries = value["mutation_boundaries"]
    assert isinstance(authority, dict)
    assert isinstance(boundaries, dict)

    assert value["status"] == "repository-only-prepared-not-authorised-not-executed"
    assert authority["microsoft_mutation_authorised"] is False
    assert authority["expired_uwc_acceptcapture_v1_authority_reusable"] is False
    assert authority["fresh_owner_go_required"] is True
    assert authority["fresh_time_bounded_window_required"] is True
    assert "no Microsoft authentication required" in boundaries["this_repository_stage"]


def test_proposal_binds_only_the_reviewed_core_resources() -> None:
    resources = _proposal()["eventual_resources"]
    assert isinstance(resources, dict)

    assert resources["environment"]["id"] == (
        "Default-aae6ab79-45eb-4829-a04f-595becdb936d"
    )
    assert resources["sharepoint_site"]["site_id"] == (
        "49cc1059-a4f6-42f7-88bd-9940503ae28f"
    )
    assert resources["work_log"]["list_id"] == (
        "7b6d10ec-c009-422a-9802-c907d3d4f57f"
    )
    assert resources["projects"]["list_id"] == (
        "66944251-b9a3-40cc-9a59-05538e200c19"
    )
    assert resources["clients"]["list_id"] == (
        "3d55c612-9799-4462-9474-7f0ca5a10b24"
    )
    assert resources["power_app"]["app_id"] == (
        "a47efc3e-0b52-405a-a220-54930a4ffdc9"
    )
    assert resources["acceptance_flow"]["exists"] is False


def test_proposal_preserves_schema_and_idempotency_boundaries() -> None:
    value = _proposal()
    fields = value["sharepoint_fields"]
    idempotency = value["idempotency"]
    assert isinstance(fields, dict)
    assert isinstance(idempotency, dict)

    assert fields["schema_changes_in_this_stage"] is False
    assert len(fields["activated_optional"]) == 29
    assert set(fields["dormant_not_to_create"]) == {
        "WorkStartedAt",
        "RateClass",
        "BillingCode",
        "TechnicalValue",
        "TechnicalNote",
    }
    assert idempotency["lookup_field"] == "WorkCaptureSubmissionKey"
    assert idempotency["same_key_same_payload"] == (
        "return the existing success receipt without a create"
    )
    assert idempotency["same_key_different_payload"] == (
        "abort with an idempotency conflict and perform no mutation"
    )


def test_proposal_has_abort_rollback_validation_and_next_gate() -> None:
    value = _proposal()
    assert len(value["abort_conditions"]) >= 8
    assert isinstance(value["rollback"], dict)
    assert len(value["validation"]) >= 8
    assert "fresh" in str(value["next_gate"]).lower()
    assert "owner" in str(value["next_gate"]).lower()
