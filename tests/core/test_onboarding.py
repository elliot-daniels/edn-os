from datetime import UTC, datetime

from edn.core import (
    AuthenticationStatus,
    CapabilityManifest,
    CapabilityOnboardingPlanner,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    CapabilityValueProfile,
    OnboardingRequestStatus,
    SecurityDomain,
)

NOW = datetime(2026, 8, 12, tzinfo=UTC)
DOMAIN = SecurityDomain("EDN", "EDN Systems", "edn-local")


def _register(
    registry: CapabilityRegistry,
    capability_id: str,
    status: CapabilityStatus,
    *,
    permissions: tuple[str, ...] = (),
) -> None:
    registry.register(
        CapabilityManifest(
            capability_id,
            "microsoft-graph",
            capability_id.split(".")[0],
            "0.1.0",
            frozenset({"search"}),
            frozenset({"Mail.Read"}),
            frozenset({"EDN"}),
            "read",
        ),
        CapabilityRuntimeState(
            status,
            AuthenticationStatus.MISSING
            if status is CapabilityStatus.AUTHENTICATION_REQUIRED
            else AuthenticationStatus.NOT_REQUIRED,
            missing_permissions=permissions,
            health="unknown",
            last_verified_at=NOW,
            explanation="Declared synthetic readiness.",
        ),
    )


def _profile(
    capability_id: str,
    *,
    decision_value: int,
    record_count: int | None = None,
    byte_count: int | None = None,
) -> CapabilityValueProfile:
    return CapabilityValueProfile(
        capability_id,
        "search",
        decision_value,
        recurrence=3,
        freshness=4,
        administrative_leverage=3,
        information_density=3,
        record_count=record_count,
        byte_count=byte_count,
        exact_scope=("mailbox-owner", "folder-inbox"),
    )


def test_onboarding_reports_readiness_exact_steps_and_rejectable_request() -> None:
    registry = CapabilityRegistry()
    _register(
        registry,
        "outlook.search",
        CapabilityStatus.AUTHENTICATION_REQUIRED,
        permissions=("Mail.Read",),
    )

    item = CapabilityOnboardingPlanner().plan(
        registry,
        (_profile("outlook.search", decision_value=5),),
        DOMAIN,
    )[0]

    assert item.readiness is CapabilityStatus.AUTHENTICATION_REQUIRED
    assert item.missing_steps == ("Mail.Read", "interactive-authentication")
    assert item.request is not None
    assert item.request.exact_scope == ("mailbox-owner", "folder-inbox")
    assert item.request.required_permissions == ("Mail.Read",)
    assert item.request.reject().status is OnboardingRequestStatus.REJECTED


def test_capacity_counts_do_not_affect_value_ranking() -> None:
    registry = CapabilityRegistry()
    _register(registry, "calendar.search", CapabilityStatus.READY)
    _register(registry, "files.search", CapabilityStatus.READY)
    profiles = (
        _profile("files.search", decision_value=1, record_count=1_000_000),
        _profile("calendar.search", decision_value=5, record_count=1),
    )

    ranked = CapabilityOnboardingPlanner().plan(registry, profiles, DOMAIN)

    assert [item.capability_id for item in ranked] == [
        "calendar.search",
        "files.search",
    ]
    assert ranked[1].capacity_record_count == 1_000_000


def test_unknown_capability_fails_closed_without_fabricating_request() -> None:
    item = CapabilityOnboardingPlanner().plan(
        CapabilityRegistry(),
        (_profile("unknown.search", decision_value=5),),
        DOMAIN,
    )[0]

    assert item.readiness is CapabilityStatus.INDETERMINATE
    assert item.request is None
