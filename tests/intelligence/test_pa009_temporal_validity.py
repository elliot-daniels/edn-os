"""PA-009 freshness derivation and time-invalid statement rejection."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from edn.core import (
    Classification,
    EvidenceRef,
    SecurityDomain,
    SourceRef,
    UniversalRecordRef,
)
from edn.intelligence import (
    ContextEvidence,
    FreshnessState,
    ModelRequest,
    ProjectedEvidence,
    TemporalState,
)
from edn.intelligence.model_boundary import DisclosureProjection
from edn.intelligence.openai_provider import (
    PilotDispatchError,
    ProviderValidationReason,
    ProviderValidationStage,
    _parse_response,
    _request_payload,
)
from edn.intelligence.temporal import temporal_state

ADELAIDE = ZoneInfo("Australia/Adelaide")
REFERENCE = datetime(2026, 8, 16, 2, 3, 21, tzinfo=UTC)
DOMAIN = SecurityDomain("EDN", "EDN")
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)


def _evidence(
    timestamp: datetime | None,
    kind: str | None,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    source_label: str = "Inbox",
) -> ContextEvidence:
    source = SourceRef("source", "synthetic", "fixture", source_label)
    record = UniversalRecordRef(source, "record", DOMAIN, CLASSIFICATION, "metadata")
    return ContextEvidence(
        "context-1",
        "metadata.search",
        source_label,
        "Bounded metadata",
        "Authorised metadata only",
        1.0,
        (EvidenceRef("evidence-1", record),),
        timestamp,
        kind,
        FreshnessState.UNKNOWN,
        start,
        end,
    )


@pytest.mark.parametrize(
    ("item", "expected"),
    (
        (
            _evidence(
                REFERENCE - timedelta(days=1),
                "calendar_event_end",
                start=REFERENCE - timedelta(hours=2),
                end=REFERENCE - timedelta(hours=1),
                source_label="Calendar",
            ),
            TemporalState.EXPIRED_PAST_EVENT,
        ),
        (
            _evidence(
                REFERENCE + timedelta(hours=1),
                "calendar_event_end",
                start=REFERENCE - timedelta(hours=1),
                end=REFERENCE + timedelta(hours=1),
                source_label="Calendar",
            ),
            TemporalState.CURRENT_RECENT,
        ),
        (
            _evidence(
                REFERENCE + timedelta(hours=2),
                "calendar_event_end",
                start=REFERENCE + timedelta(hours=1),
                end=REFERENCE + timedelta(hours=2),
                source_label="Calendar",
            ),
            TemporalState.FUTURE,
        ),
        (
            _evidence(REFERENCE - timedelta(days=8), "mail_received_at"),
            TemporalState.STALE_HISTORICAL,
        ),
        (
            _evidence(REFERENCE - timedelta(days=2), "mail_received_at"),
            TemporalState.CURRENT_RECENT,
        ),
        (
            _evidence(REFERENCE - timedelta(days=31), "file_modified_at"),
            TemporalState.STALE_HISTORICAL,
        ),
        (
            _evidence(REFERENCE - timedelta(days=3), "file_modified_at"),
            TemporalState.CURRENT_RECENT,
        ),
        (_evidence(None, None), TemporalState.UNKNOWN_UNDETERMINED),
    ),
)
def test_closed_temporal_taxonomy(
    item: ContextEvidence, expected: TemporalState
) -> None:
    assert temporal_state(item, REFERENCE) is expected


def test_malformed_timestamp_fails_closed() -> None:
    malformed = cast(
        ContextEvidence,
        SimpleNamespace(
            timestamp_kind="mail_received_at",
            source_timestamp="not-a-timestamp",
            temporal_start=None,
            temporal_end=None,
        ),
    )
    assert temporal_state(malformed, REFERENCE) is TemporalState.UNKNOWN_UNDETERMINED


def test_timezone_midnight_and_day_rollover_use_instants() -> None:
    local_reference = datetime(2026, 8, 16, 0, 5, tzinfo=ADELAIDE)
    ended_previous_day = _evidence(
        datetime(2026, 8, 15, 23, 59, tzinfo=ADELAIDE),
        "calendar_event_end",
        start=datetime(2026, 8, 15, 23, 0, tzinfo=ADELAIDE),
        end=datetime(2026, 8, 15, 23, 59, tzinfo=ADELAIDE),
        source_label="Calendar",
    )
    assert (
        temporal_state(ended_previous_day, local_reference)
        is TemporalState.EXPIRED_PAST_EVENT
    )
    assert (
        temporal_state(ended_previous_day, local_reference.astimezone(UTC))
        is TemporalState.EXPIRED_PAST_EVENT
    )


def _request(state: TemporalState) -> ModelRequest:
    item = ProjectedEvidence(
        "disclosed-calendar-1",
        "Calendar",
        "Historical event metadata",
        "Bounded event metadata",
        FreshnessState.STALE,
        "digest",
        datetime(2026, 8, 13, 1, tzinfo=UTC),
        "calendar.metadata",
        True,
        state,
    )
    projection = DisclosureProjection(
        "pa009-temporal-regression", (item,), 42, reference_time=REFERENCE
    )
    return ModelRequest(
        projection.request_id,
        "daily-intelligence",
        "owner",
        "EDN",
        (item.disclosure_id,),
        projection,
        CLASSIFICATION,
        "model.summarize",
        5,
        synthetic_fixture=False,
    )


def _response(kind: str, text: str, *, proposal_only: bool) -> dict[str, object]:
    statement = {
        "kind": kind,
        "text": text,
        "disclosed_evidence_ids": ["disclosed-calendar-1"],
        "uncertainty": "model-generated inference",
        "proposal_only": proposal_only,
    }
    return {
        "object": "response",
        "id": "response-1",
        "provider": "openai.api",
        "model": "gpt-5-mini-2025-08-07",
        "metadata": {
            "edn_request_id": "pa009-temporal-regression",
            "edn_provider_id": "openai.api",
            "edn_model": "gpt-5-mini-2025-08-07",
            "edn_policy_id": "openai-daily-brief-pilot-v1",
        },
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"statements": [statement]}),
                    }
                ],
            }
        ],
    }


def test_exact_retained_result_defect_is_reproduced_and_rejected() -> None:
    request = _request(TemporalState.EXPIRED_PAST_EVENT)
    with pytest.raises(PilotDispatchError) as exc:
        _parse_response(
            _response(
                "proposed_action",
                "Prepare before the 2026-08-13 meeting.",
                proposal_only=True,
            ),
            request,
            "gpt-5-mini-2025-08-07",
        )
    assert exc.value.validation_stage is ProviderValidationStage.TEMPORAL
    assert (
        exc.value.validation_reason is ProviderValidationReason.TEMPORAL_CLAIM_INVALID
    )


def test_preflight_rejects_manually_mislabelled_past_calendar_metadata() -> None:
    from edn.intelligence import (
        InMemoryProviderAudit,
        OpenAIDisclosurePolicy,
        OpenAIPilotConfig,
        OpenAIProvider,
        PilotBudgetLedger,
    )

    request = _request(TemporalState.CURRENT_RECENT)
    provider = OpenAIProvider(
        config=OpenAIPilotConfig(enabled=True),
        policy=OpenAIDisclosurePolicy(
            "owner-pilot",
            "owner-approval",
            CLASSIFICATION,
            frozenset({"EDN"}),
            frozenset({"calendar.metadata"}),
            True,
        ),
        budget=PilotBudgetLedger(),
        audit=InMemoryProviderAudit(),
    )
    preflight = provider.preflight(request)
    assert not preflight.dispatch_permitted
    assert preflight.refusal_reason == "disclosure_denied"


def test_stale_evidence_cannot_support_an_elapsed_action_deadline() -> None:
    request = _request(TemporalState.STALE_HISTORICAL)
    with pytest.raises(PilotDispatchError) as exc:
        _parse_response(
            _response(
                "proposed_action",
                "Complete the action by 2026-08-13.",
                proposal_only=True,
            ),
            request,
            "gpt-5-mini-2025-08-07",
        )
    assert exc.value.validation_stage is ProviderValidationStage.TEMPORAL


@pytest.mark.parametrize(
    ("kind", "text", "proposal_only"),
    (
        ("model_assertion", "The cited meeting occurred in the past.", False),
        (
            "proposed_action",
            "Consider following up on unresolved meeting consequences.",
            True,
        ),
    ),
)
def test_historical_evidence_remains_useful(
    kind: str, text: str, proposal_only: bool
) -> None:
    parsed = _parse_response(
        _response(kind, text, proposal_only=proposal_only),
        _request(TemporalState.EXPIRED_PAST_EVENT),
        "gpt-5-mini-2025-08-07",
    )
    assert parsed.statements[0].text == text


def test_projection_exposes_only_bounded_temporal_state_and_reference() -> None:
    payload = _request_payload(
        _request(TemporalState.EXPIRED_PAST_EVENT), "gpt-5-mini-2025-08-07"
    )
    serialized = json.dumps(payload)
    assert "temporal_state" in serialized
    assert "expired_past_event" in serialized
    assert REFERENCE.isoformat() in serialized
    assert "temporal_start" not in serialized
    assert "temporal_end" not in serialized


def test_synthetic_and_genuine_labels_do_not_change_temporal_rules() -> None:
    synthetic = _evidence(
        REFERENCE - timedelta(days=8),
        "mail_received_at",
        source_label="Synthetic Inbox",
    )
    genuine = _evidence(
        REFERENCE - timedelta(days=8),
        "mail_received_at",
        source_label="Current Outlook mail",
    )
    assert temporal_state(synthetic, REFERENCE) is temporal_state(genuine, REFERENCE)
