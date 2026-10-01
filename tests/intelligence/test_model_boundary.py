"""Synthetic-only model/disclosure boundary conformance tests."""

# ruff: noqa: E501 -- conformance cases keep policy combinations explicit.

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from edn.core import (
    Classification,
    EvidenceRef,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    SourceRef,
    UniversalRecordRef,
)
from edn.intelligence import (
    AssembledContext,
    ContextEvidence,
    DisclosureOutcome,
    DisclosurePolicy,
    FreshnessState,
    IntelligenceRequest,
    ModelIntelligenceBoundary,
    ModelStatementKind,
)

NOW = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)
EDN = SecurityDomain("EDN", "EDN", tenant_id="tenant")
CLIENT = SecurityDomain("CLIENT:alpha", "Client Alpha", tenant_id="tenant")
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)
RESTRICTED = Classification("edn", "restricted", "EDN Restricted", 3)
UNKNOWN = Classification("edn", "unknown", "Unknown", None)
PURPOSE = Purpose("morning-brief", "Synthetic morning briefing")


def _context(*items: ContextEvidence, domain: SecurityDomain = EDN) -> AssembledContext:
    principal = PrincipalContext("owner", "tenant", frozenset({domain}), True)
    request = IntelligenceRequest(
        "What matters this morning?", principal, PURPOSE, domain, CLASSIFICATION
    )
    return AssembledContext(request, tuple(items), ())


def _item(
    suffix: str,
    *,
    classification: Classification = CLASSIFICATION,
    domain: SecurityDomain = EDN,
    freshness: FreshnessState = FreshnessState.CURRENT,
    text: str | None = None,
) -> ContextEvidence:
    source = SourceRef(f"synthetic-{suffix}", "synthetic", f"instance-{suffix}", suffix)
    record = UniversalRecordRef(
        source, f"record-{suffix}", domain, classification, "synthetic-record"
    )
    ref = EvidenceRef(f"evidence-{suffix}", record, locator="synthetic")
    return ContextEvidence(
        f"context:{suffix}",
        "synthetic.search",
        suffix,
        f"{suffix} commitment",
        text or f"Synthetic evidence for {suffix}.",
        1.0,
        (ref,),
        NOW,
        "synthetic_source_timestamp",
        freshness,
    )


def _policy(**kwargs: object) -> DisclosurePolicy:
    return DisclosurePolicy(
        authority_ref="owner-synthetic-model-review",
        classification_ceiling=CLASSIFICATION,
        allowed_domains=frozenset({EDN.domain_id}),
        **kwargs,
    )


def test_synthetic_end_to_end_preserves_freshness_gaps_and_proposal_only_output() -> None:
    context = _context(
        _item("calendar", freshness=FreshnessState.CURRENT),
        _item("customer", freshness=FreshnessState.AGEING),
        _item("project", freshness=FreshnessState.STALE),
    )
    result = ModelIntelligenceBoundary().run(
        context, policy=_policy(), request_id="model-request-brief-1"
    )

    assert result.decision.outcome is DisclosureOutcome.ALLOWED
    assert result.projection is not None
    assert {item.freshness for item in result.projection.items} == {
        FreshnessState.CURRENT,
        FreshnessState.AGEING,
        FreshnessState.STALE,
    }
    assert result.model_response is not None
    assert all(
        statement.kind is not ModelStatementKind.MODEL_ASSERTION
        or statement.uncertainty == "inference from projected evidence"
        for statement in result.model_response.statements
    )
    assert any(
        statement.kind is ModelStatementKind.PROPOSED_ACTION
        and statement.proposal_only
        for statement in result.model_response.statements
    )
    assert result.model_response.disclosed_evidence_ids == (
        "disclosed-1",
        "disclosed-2",
        "disclosed-3",
    )
    assert result.fallback_available


def test_projection_excludes_internal_identifiers_and_synthetic_sensitive_markers() -> None:
    context = _context(
        _item(
            "calendar",
            text="Visible agenda. secret=do-not-disclose raw_graph_payload=abc123",
        )
    )
    result = ModelIntelligenceBoundary().run(
        context, policy=_policy(), request_id="model-request-leak-1"
    )
    assert result.projection is not None
    visible = result.projection.items[0]
    assert "context:calendar" not in visible.excerpt
    assert "evidence-calendar" not in visible.excerpt
    assert "do-not-disclose" not in visible.excerpt
    assert "abc123" not in visible.excerpt
    assert "context:calendar:sensitive_marker" in result.projection.redactions
    assert result.model_response is not None
    assert result.model_response.disclosed_evidence_ids == ("disclosed-1",)


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (_item("restricted", classification=RESTRICTED), DisclosureOutcome.CLASSIFICATION_CEILING_EXCEEDED),
        (_item("unknown", classification=UNKNOWN), DisclosureOutcome.UNKNOWN_CLASSIFICATION),
        (_item("other-domain", domain=CLIENT), DisclosureOutcome.DENIED),
    ],
)
def test_classification_and_domain_enforcement_fails_closed(
    item: ContextEvidence, expected: DisclosureOutcome
) -> None:
    result = ModelIntelligenceBoundary().run(
        _context(item), policy=_policy(), request_id="model-request-policy-1"
    )
    assert result.decision.outcome is expected
    assert result.projection is None
    assert result.model_response is None
    assert result.fallback_available


def test_missing_authority_and_oversized_context_fail_closed() -> None:
    missing = DisclosurePolicy(None, CLASSIFICATION, frozenset({EDN.domain_id}))
    result = ModelIntelligenceBoundary().run(
        _context(_item("calendar")), policy=missing, request_id="model-request-auth-1"
    )
    assert result.decision.outcome is DisclosureOutcome.MISSING_AUTHORITY
    assert result.fallback_reason == "missing_disclosure_authority"

    oversized = _policy(max_context_chars=10)
    result = ModelIntelligenceBoundary().run(
        _context(_item("calendar", text="A" * 500)),
        policy=oversized,
        request_id="model-request-budget-1",
    )
    assert result.decision.is_allowed
    assert result.projection is not None
    assert result.projection.total_chars <= 10
    assert result.projection.redactions


def test_mixed_classifications_are_not_partially_disclosed() -> None:
    result = ModelIntelligenceBoundary().run(
        _context(_item("allowed"), _item("restricted", classification=RESTRICTED)),
        policy=_policy(),
        request_id="model-request-mixed-1",
    )
    assert result.decision.outcome is DisclosureOutcome.CLASSIFICATION_CEILING_EXCEEDED
    assert result.projection is None


def test_provider_failure_keeps_local_fallback_and_does_not_execute() -> None:
    class BrokenProvider:
        provider_id = "synthetic.broken"

        def generate(self, request: object) -> object:
            del request
            raise RuntimeError("synthetic provider unavailable")

    result = ModelIntelligenceBoundary(provider=BrokenProvider()).run(
        _context(_item("calendar")),
        policy=_policy(),
        request_id="model-request-failure-1",
    )
    assert result.model_response is None
    assert result.fallback_available
    assert result.fallback_reason == "runtimeerror"
