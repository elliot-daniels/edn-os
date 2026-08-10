"""Stable contracts for Intelligence Core consumers."""

from edn.core.capabilities import (
    CapabilityDecision,
    CapabilityManifest,
    CapabilityStatus,
)
from edn.core.permissions import (
    PermissionDecision,
    PermissionOutcome,
    PermissionRequest,
)
from edn.core.policy import (
    CapabilityUseDecision,
    PermissionEvaluator,
    PolicyRule,
    PolicySet,
    UseDecisionOutcome,
    evaluate_capability_use,
    evaluate_operation_candidates,
)
from edn.core.references import (
    EvidenceRef,
    SourceRef,
    UniversalRecordRef,
    count_eligible_evidence,
    filter_eligible_evidence,
    is_evidence_eligible,
)
from edn.core.registry import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
    RegisteredCapability,
)
from edn.core.security import Classification, PrincipalContext, Purpose, SecurityDomain

__all__ = [
    "AuthenticationStatus",
    "CapabilityDecision",
    "CapabilityManifest",
    "CapabilityRegistry",
    "CapabilityRuntimeState",
    "CapabilityStatus",
    "CapabilityUseDecision",
    "Classification",
    "EvidenceRef",
    "PermissionDecision",
    "PermissionEvaluator",
    "PermissionOutcome",
    "PermissionRequest",
    "PolicyRule",
    "PolicySet",
    "PrincipalContext",
    "Purpose",
    "RegisteredCapability",
    "SecurityDomain",
    "SourceRef",
    "UniversalRecordRef",
    "UseDecisionOutcome",
    "count_eligible_evidence",
    "evaluate_capability_use",
    "evaluate_operation_candidates",
    "filter_eligible_evidence",
    "is_evidence_eligible",
]
