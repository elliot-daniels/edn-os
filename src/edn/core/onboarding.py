"""Deterministic, authority-safe progressive capability onboarding."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from edn.core.capabilities import CapabilityDecision, CapabilityStatus
from edn.core.registry import CapabilityRegistry, RegisteredCapability
from edn.core.security import SecurityDomain, validate_identifier


class OnboardingRequestStatus(StrEnum):
    PENDING = "pending"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CapabilityValueProfile:
    """Owner-value inputs; capacity facts are intentionally scored separately."""

    capability_id: str
    operation: str
    decision_value: int
    recurrence: int
    freshness: int
    administrative_leverage: int
    information_density: int
    record_count: int | None = None
    byte_count: int | None = None
    exact_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.capability_id, "capability_id")
        validate_identifier(self.operation, "operation")
        for name in (
            "decision_value",
            "recurrence",
            "freshness",
            "administrative_leverage",
            "information_density",
        ):
            if not 0 <= getattr(self, name) <= 5:
                raise ValueError(f"{name} must be between 0 and 5")
        for name in ("record_count", "byte_count"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")
        if len(set(self.exact_scope)) != len(self.exact_scope):
            raise ValueError("exact_scope must not contain duplicates")
        for scope in self.exact_scope:
            validate_identifier(scope, "exact_scope")

    @property
    def value_score(self) -> int:
        """Rank by value, never by record count or bytes."""
        return (
            self.decision_value * 5
            + self.recurrence * 4
            + self.freshness * 4
            + self.administrative_leverage * 3
            + self.information_density * 2
        )


@dataclass(frozen=True, slots=True)
class OnboardingRequest:
    request_id: str
    capability_id: str
    operation: str
    provider_id: str
    connector_id: str
    domain_id: str
    exact_scope: tuple[str, ...]
    required_permissions: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    status: OnboardingRequestStatus = OnboardingRequestStatus.PENDING

    def reject(self) -> OnboardingRequest:
        return replace(self, status=OnboardingRequestStatus.REJECTED)


@dataclass(frozen=True, slots=True)
class OnboardingRecommendation:
    capability_id: str
    readiness: CapabilityStatus
    readiness_explanation: str
    missing_steps: tuple[str, ...]
    value_score: int
    capacity_record_count: int | None
    capacity_byte_count: int | None
    request: OnboardingRequest | None


class CapabilityOnboardingPlanner:
    """Build ranked recommendations from declared, non-probed runtime facts."""

    def plan(
        self,
        registry: CapabilityRegistry,
        profiles: tuple[CapabilityValueProfile, ...],
        domain: SecurityDomain,
    ) -> tuple[OnboardingRecommendation, ...]:
        recommendations: list[OnboardingRecommendation] = []
        for profile in profiles:
            registered = registry.get(profile.capability_id)
            decision = registry.resolve(
                profile.capability_id, profile.operation, domain
            )
            steps = _missing_steps(decision, registered)
            request = _request(profile, registered, domain, decision, steps)
            recommendations.append(
                OnboardingRecommendation(
                    profile.capability_id,
                    decision.status,
                    decision.explanation,
                    steps,
                    profile.value_score,
                    profile.record_count,
                    profile.byte_count,
                    request,
                )
            )
        return tuple(
            sorted(
                recommendations,
                key=lambda item: (-item.value_score, item.capability_id),
            )
        )


def _missing_steps(
    decision: CapabilityDecision, registered: RegisteredCapability | None
) -> tuple[str, ...]:
    if decision.status is CapabilityStatus.READY:
        return ()
    steps = (
        []
        if decision.status is CapabilityStatus.AUTHENTICATION_REQUIRED
        else list(decision.missing_requirements)
    )
    if registered is not None:
        runtime = registered.runtime
        steps.extend(runtime.unavailable_dependencies)
        steps.extend(runtime.missing_permissions)
        if decision.status is CapabilityStatus.AUTHENTICATION_REQUIRED:
            steps.append("interactive-authentication")
        elif decision.status is CapabilityStatus.APPROVAL_REQUIRED:
            steps.append("owner-approval")
        elif decision.status is CapabilityStatus.PERMISSION_REQUIRED:
            steps.append("exact-permission-grant")
    return tuple(dict.fromkeys(steps))


def _request(
    profile: CapabilityValueProfile,
    registered: RegisteredCapability | None,
    domain: SecurityDomain,
    decision: CapabilityDecision,
    steps: tuple[str, ...],
) -> OnboardingRequest | None:
    if decision.status is CapabilityStatus.READY or registered is None:
        return None
    manifest = registered.manifest
    return OnboardingRequest(
        f"onboard-{profile.capability_id.replace('.', '-')}",
        profile.capability_id,
        profile.operation,
        manifest.provider_id,
        manifest.connector_id,
        domain.domain_id,
        profile.exact_scope,
        tuple(sorted(manifest.required_permissions)),
        steps,
    )
