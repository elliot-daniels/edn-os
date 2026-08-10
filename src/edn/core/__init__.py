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
from edn.core.references import (
    EvidenceRef,
    SourceRef,
    UniversalRecordRef,
    count_eligible_evidence,
    filter_eligible_evidence,
    is_evidence_eligible,
)
from edn.core.security import Classification, PrincipalContext, Purpose, SecurityDomain

__all__ = [
    "CapabilityDecision",
    "CapabilityManifest",
    "CapabilityStatus",
    "Classification",
    "EvidenceRef",
    "PermissionDecision",
    "PermissionOutcome",
    "PermissionRequest",
    "PrincipalContext",
    "Purpose",
    "SecurityDomain",
    "SourceRef",
    "UniversalRecordRef",
    "count_eligible_evidence",
    "filter_eligible_evidence",
    "is_evidence_eligible",
]
