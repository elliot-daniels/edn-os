"""Synthetic PA-007 freshness-aware Daily Intelligence acceptance tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from edn.core import (
    CapabilityManifest,
    Classification,
    EvidenceRef,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    SourceRef,
    UniversalRecordRef,
)
from edn.core.capabilities import CapabilityStatus
from edn.core.permissions import PermissionOutcome
from edn.core.policy import PermissionEvaluator, PolicyRule, PolicySet
from edn.core.registry import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
)
from edn.intelligence import (
    BriefSectionKind,
    ContextAssembler,
    ContextEvidence,
    DailyIntelligenceComposer,
    FreshnessState,
    IntelligenceRequest,
    IntelligenceService,
    StatementKind,
)

NOW = datetime(2026, 8, 13, 8, 0, tzinfo=UTC)
DOMAIN = SecurityDomain("EDN", "EDN", tenant_id="edn-local")
CLASSIFICATION = Classification("edn", "confidential", "Confidential", 2)
PURPOSE = Purpose("daily-brief", "Prepare today's priorities")
PRINCIPAL = PrincipalContext("owner", "edn-local", frozenset({DOMAIN}), True)


def _request() -> IntelligenceRequest:
    return IntelligenceRequest(
        "Build my brief", PRINCIPAL, PURPOSE, DOMAIN, CLASSIFICATION
    )


@dataclass
class SyntheticAdapter:
    capability_id: str
    source_label: str
    title: str
    source_timestamp: datetime | None
    count: int = 1
    operation: str = "evidence.retrieve"
    resource_scope: tuple[str, ...] = ()

    def retrieve(self, request, *, limit, now, authority):
        del now, authority
        source = SourceRef(
            self.capability_id, "synthetic", self.capability_id, self.source_label
        )
        return tuple(
            ContextEvidence(
                f"{self.capability_id}:{index}",
                self.capability_id,
                self.source_label,
                self.title if index == 0 else f"{self.title} {index}",
                f"Synthetic {self.source_label} evidence {index}.",
                float(limit - index),
                (
                    EvidenceRef(
                        f"evidence-{self.capability_id}-{index}",
                        UniversalRecordRef(
                            source,
                            f"record-{index}",
                            request.security_domain,
                            request.classification,
                            "synthetic",
                        ),
                        locator=f"synthetic locator {index}",
                    ),
                ),
                self.source_timestamp,
                "synthetic_source_timestamp"
                if self.source_timestamp is not None
                else None,
            )
            for index in range(min(limit, self.count))
        )


def _service(*adapters: SyntheticAdapter) -> IntelligenceService:
    registry = CapabilityRegistry()
    rules = []
    for adapter in adapters:
        registry.register(
            CapabilityManifest(
                adapter.capability_id,
                "synthetic",
                "brief-fixture",
                "1",
                frozenset({adapter.operation}),
                frozenset(),
                frozenset({DOMAIN.domain_id}),
                "read",
            ),
            CapabilityRuntimeState(
                CapabilityStatus.READY, AuthenticationStatus.NOT_REQUIRED
            ),
        )
        rules.append(
            PolicyRule(
                f"allow-{adapter.capability_id}",
                PermissionOutcome.ALLOWED,
                "Synthetic local test authority.",
                capability_ids=frozenset({adapter.capability_id}),
                operations=frozenset({adapter.operation}),
            )
        )
    return IntelligenceService(
        ContextAssembler(
            registry,
            PermissionEvaluator(PolicySet("brief-test", "1", tuple(rules))),
            adapters,
            per_source_limit=10,
            total_limit=10,
        )
    )


def _mixed_service() -> IntelligenceService:
    return _service(
        SyntheticAdapter(
            "calendar.search",
            "Calendar",
            "Project Atlas review",
            NOW + timedelta(hours=4),
        ),
        SyntheticAdapter(
            "outlook.search",
            "Current Outlook mail",
            "Project Atlas review",
            NOW - timedelta(hours=5),
        ),
        SyntheticAdapter(
            "local-files.search",
            "Local document",
            "Operating plan",
            NOW - timedelta(days=15),
        ),
    )


def test_brief_has_canonical_sections_and_typed_epistemic_items() -> None:
    response = _mixed_service().daily_brief(_request(), now=NOW)

    assert response.daily_brief is not None
    assert tuple(section.kind for section in response.daily_brief.sections) == tuple(
        BriefSectionKind
    )
    assert any(item.kind is StatementKind.FACT for item in response.daily_brief.items)
    assert any(
        item.kind is StatementKind.INFERENCE for item in response.daily_brief.items
    )
    assert all(
        item.evidence_ids
        for item in response.daily_brief.items
        if item.kind is StatementKind.FACT
    )
    assert all(
        not item.evidence_ids
        for item in response.daily_brief.items
        if item.kind is StatementKind.UNKNOWN
    )


def test_freshness_is_source_timestamp_and_policy_driven() -> None:
    response = _service(
        SyntheticAdapter("calendar.search", "Calendar", "Fresh meeting", NOW),
        SyntheticAdapter(
            "outlook.search",
            "Current Outlook mail",
            "Ageing mail",
            NOW - timedelta(days=3),
        ),
        SyntheticAdapter(
            "local-files.search",
            "Local document",
            "Stale plan",
            NOW - timedelta(days=45),
        ),
        SyntheticAdapter("email.retrieve", "Email memory", "Undated history", None),
    ).daily_brief(_request(), now=NOW)

    assert response.daily_brief is not None
    freshness = {
        item.title: item.freshness
        for item in response.daily_brief.items
        if item.kind is StatementKind.FACT
    }
    assert freshness == {
        "Fresh meeting": FreshnessState.CURRENT,
        "Ageing mail": FreshnessState.AGEING,
        "Stale plan": FreshnessState.STALE,
        "Undated history": FreshnessState.UNKNOWN,
    }


def test_stale_and_unknown_evidence_cannot_enter_immediate_attention() -> None:
    response = _service(
        SyntheticAdapter(
            "local-files.search",
            "Local document",
            "Stale plan",
            NOW - timedelta(days=45),
        ),
        SyntheticAdapter("email.retrieve", "Email memory", "Undated history", None),
    ).daily_brief(_request(), now=NOW)

    assert response.daily_brief is not None
    attention = next(
        section
        for section in response.daily_brief.sections
        if section.kind is BriefSectionKind.IMMEDIATE_ATTENTION
    )
    risks = next(
        section
        for section in response.daily_brief.sections
        if section.kind is BriefSectionKind.RISKS_GAPS
    )
    assert attention.items == ()
    assert {item.freshness for item in risks.items} >= {
        FreshnessState.STALE,
        FreshnessState.UNKNOWN,
    }


def test_missing_sources_are_explicit_gaps_not_nothing_to_report() -> None:
    response = _service().daily_brief(_request(), now=NOW)

    assert response.priorities == ()
    assert response.statements[0].kind is StatementKind.UNKNOWN
    assert response.daily_brief is not None
    gaps = [
        item
        for item in response.daily_brief.items
        if item.section is BriefSectionKind.RISKS_GAPS
    ]
    assert {item.item_id for item in gaps} == {
        "gap:calendar.search",
        "gap:outlook.search",
        "gap:local-files.search",
    }
    assert all("completeness is unknown" in item.text for item in gaps)


def test_exact_title_cross_source_corroboration_affects_rank_deterministically() -> (
    None
):
    response = _mixed_service().daily_brief(_request(), now=NOW)

    assert response.daily_brief is not None
    facts = [
        item for item in response.daily_brief.items if item.kind is StatementKind.FACT
    ]
    atlas = [item for item in facts if item.title == "Project Atlas review"]
    assert len(atlas) == 2
    assert all("corroborating_source_families=2" in item.rank_reasons for item in atlas)
    repeated = _mixed_service().daily_brief(_request(), now=NOW)
    assert repeated.daily_brief == response.daily_brief


def test_record_volume_does_not_change_source_value_factors() -> None:
    response = _service(
        SyntheticAdapter("calendar.search", "Calendar", "Owner decision", NOW, count=1),
        SyntheticAdapter(
            "email.retrieve",
            "Email memory",
            "Historical item",
            NOW - timedelta(days=1),
            count=9,
        ),
    ).daily_brief(_request(), now=NOW)

    assert response.daily_brief is not None
    facts = [
        item for item in response.daily_brief.items if item.kind is StatementKind.FACT
    ]
    calendar = next(item for item in facts if item.title == "Owner decision")
    email = next(item for item in facts if item.title == "Historical item")
    assert calendar.rank_score > email.rank_score
    assert all("volume" not in reason for item in facts for reason in item.rank_reasons)


def test_suggested_actions_are_explicitly_non_executing_proposals() -> None:
    response = _mixed_service().daily_brief(_request(), now=NOW)

    assert response.daily_brief is not None
    actions = [
        item
        for item in response.daily_brief.items
        if item.section is BriefSectionKind.SUGGESTED_ACTIONS
    ]
    assert actions
    assert all(item.kind is StatementKind.PROPOSED_ACTION for item in actions)
    assert all(item.proposal_only for item in actions)
    assert all("do not send" in item.text for item in actions)
    assert response.proposed_actions == ()


def test_composer_enforces_architectural_maximum() -> None:
    with pytest.raises(ValueError, match="zero and ten"):
        DailyIntelligenceComposer(11)
