"""Synthetic security, provenance, session, and multi-source IC-008 tests."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    EmailRetrievalAdapter,
    GlobalKnowledge,
    IntelligenceRequest,
    IntelligenceService,
    IntelligenceStatement,
    StatementKind,
)
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import RetrievalEngine

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
EDN = SecurityDomain("EDN", "EDN", tenant_id="tenant")
PERSONAL = SecurityDomain("PERSONAL", "Personal", tenant_id="tenant")
CLIENT = SecurityDomain.scoped(
    "CLIENT", "alpha", label="Client Alpha", tenant_id="tenant"
)
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)
PURPOSE = Purpose("weekly-review", "Prepare weekly priorities")


def _principal(*domains: SecurityDomain) -> PrincipalContext:
    return PrincipalContext("elliot", "tenant", frozenset(domains), True)


def _request(domain: SecurityDomain = EDN) -> IntelligenceRequest:
    return IntelligenceRequest(
        "What matters this week?",
        _principal(domain),
        PURPOSE,
        domain,
        CLASSIFICATION,
    )


def _evidence(
    request: IntelligenceRequest,
    capability_id: str,
    suffix: str,
    source_label: str | None = None,
) -> ContextEvidence:
    source = SourceRef(f"source-{suffix}", "synthetic", f"instance-{suffix}", suffix)
    record = UniversalRecordRef(
        source,
        f"record-{suffix}",
        request.security_domain,
        request.classification,
        "synthetic-record",
    )
    reference = EvidenceRef(f"evidence-{suffix}", record, locator="synthetic excerpt")
    return ContextEvidence(
        f"context:{suffix}",
        capability_id,
        source_label or suffix,
        f"Title {suffix}",
        f"Useful private evidence from {suffix}.",
        1.0,
        (reference,),
    )


@dataclass
class FakeAdapter:
    capability_id: str
    suffix: str
    operation: str = "evidence.retrieve"
    calls: list[str] = field(default_factory=list)
    returned_domain: SecurityDomain | None = None
    resource_scope: tuple[str, ...] = ()
    count: int = 1

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: object,
    ) -> tuple[ContextEvidence, ...]:
        del now, authority
        self.calls.append(request.security_domain.domain_id)
        evidence_request = request
        if self.returned_domain is not None:
            evidence_request = IntelligenceRequest(
                request.query,
                _principal(self.returned_domain),
                request.purpose,
                self.returned_domain,
                request.classification,
            )
        return tuple(
            _evidence(
                evidence_request,
                self.capability_id,
                f"{self.suffix}-{index}",
                self.suffix,
            )
            for index in range(min(limit, self.count))
        )


def _assembler(
    adapters: tuple[FakeAdapter, ...], *, allowed: frozenset[str] | None = None
) -> ContextAssembler:
    registry = CapabilityRegistry()
    for adapter in adapters:
        registry.register(
            CapabilityManifest(
                adapter.capability_id,
                "test-provider",
                "synthetic",
                "1.0",
                frozenset({adapter.operation}),
                frozenset(),
                frozenset({EDN.domain_id, PERSONAL.domain_id, CLIENT.domain_id}),
                "low",
            ),
            CapabilityRuntimeState(
                CapabilityStatus.READY, AuthenticationStatus.NOT_REQUIRED
            ),
        )
    allowed_capabilities = allowed or frozenset(
        adapter.capability_id for adapter in adapters
    )
    policy = PermissionEvaluator(
        PolicySet(
            "test-policy",
            "1",
            tuple(
                PolicyRule(
                    f"allow-{capability_id}",
                    PermissionOutcome.ALLOWED,
                    "Synthetic test authority.",
                    capability_ids=frozenset({capability_id}),
                    operations=frozenset({"evidence.retrieve"}),
                )
                for capability_id in allowed_capabilities
            ),
        )
    )
    return ContextAssembler(registry, policy, adapters)


def test_permission_is_evaluated_before_retrieval() -> None:
    allowed = FakeAdapter("email.retrieve", "email")
    denied = FakeAdapter("personal.retrieve", "personal")

    context = _assembler(
        (allowed, denied), allowed=frozenset({allowed.capability_id})
    ).assemble(_request(), now=NOW)

    assert allowed.calls == ["EDN"]
    assert denied.calls == []
    assert context.unavailable_capabilities == (
        "personal.retrieve:permission_indeterminate",
    )


@pytest.mark.parametrize("domain", [EDN, PERSONAL, CLIENT])
def test_exact_domain_isolation(domain: SecurityDomain) -> None:
    adapter = FakeAdapter("records.retrieve", domain.domain_id.casefold())

    context = _assembler((adapter,)).assemble(_request(domain), now=NOW)

    assert len(context.evidence) == 1
    assert all(
        ref.record.security_domain == domain for ref in context.evidence[0].provenance
    )


def test_scope_mismatched_adapter_evidence_is_discarded() -> None:
    adapter = FakeAdapter("records.retrieve", "leak", returned_domain=PERSONAL)

    context = _assembler((adapter,)).assemble(_request(EDN), now=NOW)

    assert context.evidence == ()
    assert context.unavailable_capabilities == (
        "records.retrieve:evidence_scope_mismatch",
    )


def test_facts_require_private_provenance_and_global_knowledge_is_separate() -> None:
    with pytest.raises(ValueError, match="facts require private evidence"):
        IntelligenceStatement(StatementKind.FACT, "Unsupported fact")
    with pytest.raises(ValueError, match="global knowledge"):
        IntelligenceStatement(
            StatementKind.FACT,
            "General knowledge disguised as fact",
            ("context:1",),
            ("global:1",),
        )
    assert GlobalKnowledge("global:1", "Review deadlines weekly.").source_label == (
        "general model knowledge"
    )


def test_inference_is_never_silently_retyped_as_fact() -> None:
    statement = IntelligenceStatement(
        StatementKind.INFERENCE,
        "This may need attention.",
        ("context:1",),
    )
    assert statement.kind is StatementKind.INFERENCE


def test_multi_source_response_preserves_provenance() -> None:
    adapters = (
        FakeAdapter("email.retrieve", "email"),
        FakeAdapter("knowledge.retrieve", "knowledge"),
    )
    service = IntelligenceService(_assembler(adapters))

    response = service.answer(
        _request(),
        now=NOW,
        global_knowledge=(
            GlobalKnowledge("global:weekly", "Review weekly commitments."),
        ),
    )

    assert {item.capability_id for item in response.evidence} == {
        "email.retrieve",
        "knowledge.retrieve",
    }
    assert all(item.provenance for item in response.evidence)
    facts = [item for item in response.statements if item.kind is StatementKind.FACT]
    assert len(facts) == 2
    assert all(item.evidence_ids for item in facts)
    recommendation = response.statements[-1]
    assert recommendation.kind is StatementKind.RECOMMENDATION
    assert recommendation.global_knowledge_ids == ("global:weekly",)


def test_follow_up_session_cannot_widen_domain() -> None:
    service = IntelligenceService(_assembler((FakeAdapter("email.retrieve", "email"),)))
    first = service.answer(_request(EDN), now=NOW)

    with pytest.raises(PermissionError, match="original authority"):
        service.answer(_request(PERSONAL), now=NOW, session_id=first.session_id)


def test_context_balances_source_families_round_robin() -> None:
    email = FakeAdapter("email.retrieve", "email", count=5)
    calendar = FakeAdapter("calendar.retrieve", "calendar", count=5)
    assembler = _assembler((email, calendar))
    assembler.total_limit = 4

    context = assembler.assemble(_request(), now=NOW)

    assert [item.source_label for item in context.evidence] == [
        "calendar",
        "email",
        "calendar",
        "email",
    ]


def test_email_adapter_wraps_existing_retrieval_with_core_provenance(tmp_path) -> None:
    store = SQLiteEmailStore(tmp_path / "memory.db")
    store.initialise()
    store.add(
        EmailRecord(
            source_record_key="weekly-email",
            folder_path="Inbox",
            subject="Weekly project review",
            sender="engineer@example.com",
            recipients_to=("elliot@example.com",),
            recipients_cc=(),
            recipients_bcc=(),
            sent_at=NOW,
            received_at=None,
            message_id="<weekly@example.com>",
            body_text="The weekly project review requires an owner decision.",
        )
    )

    base = _request()
    request = IntelligenceRequest(
        "weekly project review",
        base.principal,
        base.purpose,
        base.security_domain,
        base.classification,
    )
    adapter = EmailRetrievalAdapter(RetrievalEngine.from_store(store))
    evidence = _assembler((adapter,)).assemble(request, now=NOW).evidence  # type: ignore[arg-type]

    assert len(evidence) == 1
    assert evidence[0].provenance[0].record.source_record_key == "weekly-email"
    assert evidence[0].provenance[0].record.security_domain == EDN
