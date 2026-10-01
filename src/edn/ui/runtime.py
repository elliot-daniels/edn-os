"""Read-only local intelligence runtime shared with the Streamlit page."""

from __future__ import annotations

from pathlib import Path

from edn.core import (
    AuthenticationStatus,
    CapabilityManifest,
    CapabilityOnboardingPlanner,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    CapabilityValueProfile,
    Classification,
    OnboardingRecommendation,
    PermissionEvaluator,
    PermissionOutcome,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
)
from edn.intelligence import (
    ActionPlanner,
    CapabilityGapAdapter,
    ContextAssembler,
    EmailRetrievalAdapter,
    IntelligenceService,
    KnowledgeGraphAdapter,
    SourceAdapter,
    SQLiteActionProposalStore,
    SQLiteSessionStore,
)
from edn.intelligence.brief import DailyIntelligenceComposer
from edn.intelligence.morning_sources import EmailCorpusAdapter
from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import (
    RetrievalEngine,
)


def _intelligence_runtime(
    store: SQLiteEmailStore,
    graph_store: KnowledgeGraphStore,
    graph_available: bool,
    operational_database_path: Path,
) -> tuple[
    IntelligenceService,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    Classification,
    tuple[tuple[str, str, str], ...],
    tuple[OnboardingRecommendation, ...],
]:
    domain = SecurityDomain("EDN", "EDN Systems", tenant_id="edn-local")
    classification = Classification("edn", "confidential", "EDN Confidential", rank=2)
    principal = PrincipalContext("local-owner", "edn-local", frozenset({domain}), True)
    purpose = Purpose("business-intelligence", "EDN business intelligence")
    adapters: list[SourceAdapter] = [
        EmailCorpusAdapter(
            EmailRetrievalAdapter(RetrievalEngine.from_store(store)),
            store,
            "local-email",
        )
    ]
    if graph_available:
        adapters.append(KnowledgeGraphAdapter(graph_store))
    adapters.append(
        CapabilityGapAdapter(
            "calendar.search", "search", ("default-calendar", "window:this-week")
        )
    )
    registry = CapabilityRegistry()
    for adapter in adapters:
        is_calendar = adapter.capability_id == "calendar.search"
        manifest = CapabilityManifest(
            adapter.capability_id,
            "microsoft-graph" if is_calendar else "edn-local",
            "microsoft-calendar" if is_calendar else "legacy-read-adapter",
            "0.1.0",
            frozenset({adapter.operation}),
            frozenset({"Calendars.Read"}) if is_calendar else frozenset(),
            frozenset({"EDN"}),
            "read",
        )
        registry.register(
            manifest,
            CapabilityRuntimeState(
                CapabilityStatus.AUTHENTICATION_REQUIRED
                if is_calendar
                else CapabilityStatus.READY,
                AuthenticationStatus.MISSING
                if is_calendar
                else AuthenticationStatus.NOT_REQUIRED,
                health="unknown" if is_calendar else "healthy",
                explanation=(
                    "Calendar read is implemented but awaits live approval "
                    "and authentication."
                    if is_calendar
                    else "Local read-only source is available."
                ),
            ),
        )
    policy = PermissionEvaluator(
        PolicySet(
            "local-alpha",
            "1",
            tuple(
                PolicyRule(
                    f"allow-{adapter.capability_id.replace('.', '-')}",
                    PermissionOutcome.ALLOWED,
                    "Local read-only Alpha authority.",
                    principal_ids=frozenset({principal.principal_id}),
                    purpose_ids=frozenset({purpose.purpose_id}),
                    domain_ids=frozenset({domain.domain_id}),
                    capability_ids=frozenset({adapter.capability_id}),
                    operations=frozenset({adapter.operation}),
                )
                for adapter in adapters
            ),
        )
    )
    sessions = SQLiteSessionStore(operational_database_path)
    actions = SQLiteActionProposalStore(operational_database_path)
    sessions.initialise()
    actions.initialise()
    health = tuple(
        (adapter.capability_id, decision.status.value, decision.explanation)
        for adapter in adapters
        for decision in (
            registry.resolve(adapter.capability_id, adapter.operation, domain),
        )
    )
    onboarding = CapabilityOnboardingPlanner().plan(
        registry,
        tuple(
            CapabilityValueProfile(
                adapter.capability_id,
                adapter.operation,
                decision_value=5 if adapter.capability_id == "calendar.search" else 4,
                recurrence=5,
                freshness=5 if adapter.capability_id == "calendar.search" else 3,
                administrative_leverage=4,
                information_density=4,
                record_count=store.count()
                if adapter.capability_id == "email.search"
                else None,
                exact_scope=("default-calendar", "window-this-week")
                if adapter.capability_id == "calendar.search"
                else ("local-authorised-store",),
            )
            for adapter in adapters
        ),
        domain,
    )
    return (
        IntelligenceService(
            ContextAssembler(registry, policy, tuple(adapters)),
            brief_composer=DailyIntelligenceComposer(deadline_priorities_only=True),
            sessions=sessions,
            action_planner=ActionPlanner(actions),
        ),
        principal,
        purpose,
        domain,
        classification,
        health,
        onboarding,
    )
