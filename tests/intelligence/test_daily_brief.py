"""Synthetic IC-010 Daily Intelligence acceptance tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
    ContextAssembler,
    ContextEvidence,
    DailyIntelligenceComposer,
    IntelligenceRequest,
    IntelligenceService,
    StatementKind,
)

NOW = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
DOMAIN = SecurityDomain("EDN", "EDN", tenant_id="tenant")
CLASSIFICATION = Classification("edn", "confidential", "Confidential", 2)
PURPOSE = Purpose("daily-brief", "Prepare today's priorities")
PRINCIPAL = PrincipalContext("owner", "tenant", frozenset({DOMAIN}), True)


def _request() -> IntelligenceRequest:
    return IntelligenceRequest(
        "Build my brief", PRINCIPAL, PURPOSE, DOMAIN, CLASSIFICATION
    )


@dataclass
class SyntheticAdapter:
    capability_id: str
    source_label: str
    count: int
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
                f"{self.source_label} priority {index}",
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


def test_daily_brief_has_zero_to_ten_deterministic_priorities() -> None:
    service = _service(
        SyntheticAdapter("calendar.search", "Calendar", 8),
        SyntheticAdapter("email.retrieve", "Email memory", 8),
    )

    first = service.daily_brief(_request(), now=NOW)
    second = service.daily_brief(_request(), now=NOW)

    assert len(first.priorities) == 10
    assert first.priorities == second.priorities
    assert [item.title for item in first.priorities[:4]] == [
        "Calendar priority 0",
        "Email memory priority 0",
        "Calendar priority 1",
        "Email memory priority 1",
    ]


def test_every_priority_is_reviewable_and_unknowns_stay_explicit() -> None:
    response = _service(
        SyntheticAdapter("calendar.search", "Calendar", 1),
        SyntheticAdapter("email.retrieve", "Email memory", 1),
    ).daily_brief(_request(), now=NOW)
    known_ids = {item.context_id for item in response.evidence}

    assert all(set(item.evidence_ids) <= known_ids for item in response.priorities)
    assert all(item.confidence == "evidence-backed" for item in response.priorities)
    assert all(item.recommended_next_step for item in response.priorities)
    assert all(item.missing_information for item in response.priorities)


def test_no_evidence_produces_zero_priorities_and_explicit_unknown() -> None:
    response = _service().daily_brief(_request(), now=NOW)

    assert response.priorities == ()
    assert response.statements[0].kind is StatementKind.UNKNOWN


def test_composer_enforces_architectural_maximum() -> None:
    with pytest.raises(ValueError, match="zero and ten"):
        DailyIntelligenceComposer(11)
