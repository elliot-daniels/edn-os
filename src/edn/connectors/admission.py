"""Source-neutral, deterministic admission audit contracts; never retrieval grants."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from edn.core import EvidenceRef


class AdmissionOutcome(StrEnum):
    ADMITTED = "admitted"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AdmissionSourceCoverage:
    source_id: str
    state: str
    checked_at: datetime | None
    relationship_count: int


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    record_key: str
    policy_id: str
    outcome: AdmissionOutcome
    reasons: tuple[str, ...]
    relationship_evidence: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.record_key or not self.policy_id or not self.reasons:
            raise ValueError("admission audit requires record, policy and reasons")
        if self.outcome is not AdmissionOutcome.ADMITTED and self.relationship_evidence:
            raise ValueError("non-admitted records cannot contribute evidence")
