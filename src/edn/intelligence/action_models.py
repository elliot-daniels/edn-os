"""Internal proposed-action contracts with no execution behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED_FOR_EXECUTION = "approved_for_execution"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ActionProposal:
    proposal_id: str
    principal_id: str
    tenant_id: str
    domain_id: str
    classification_id: tuple[str, str]
    purpose_id: str
    proposed_operation: str
    target_capability: str
    target_resource: str
    source_evidence_ids: tuple[str, ...]
    rationale: str
    confidence: str
    expected_outcome: str
    risk_level: str
    reversibility: str
    required_permission: str
    required_approval: str
    draft_text: str | None
    created_at: datetime
    expires_at: datetime | None
    status: ActionStatus
    proposal_hash: str
    human_review_ref: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.proposal_id,
            self.principal_id,
            self.tenant_id,
            self.domain_id,
            self.purpose_id,
            self.proposed_operation,
            self.target_capability,
            self.target_resource,
            self.rationale,
            self.confidence,
            self.expected_outcome,
            self.risk_level,
            self.reversibility,
            self.required_permission,
            self.required_approval,
        )
        if any(not value.strip() for value in required):
            raise ValueError("proposal fields must not be blank")
        if not self.source_evidence_ids:
            raise ValueError("proposal requires source evidence")
        if self.created_at.tzinfo is None:
            raise ValueError("proposal creation time must be timezone-aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("proposal expiry must be timezone-aware")

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "classification_id": list(self.classification_id),
            "purpose_id": self.purpose_id,
            "proposed_operation": self.proposed_operation,
            "target_capability": self.target_capability,
            "target_resource": self.target_resource,
            "source_evidence_ids": list(self.source_evidence_ids),
            "rationale": self.rationale,
            "confidence": self.confidence,
            "expected_outcome": self.expected_outcome,
            "risk_level": self.risk_level,
            "reversibility": self.reversibility,
            "required_permission": self.required_permission,
            "required_approval": self.required_approval,
            "draft_text": self.draft_text,
            "created_at": self.created_at.isoformat(),
            "expires_at": None
            if self.expires_at is None
            else self.expires_at.isoformat(),
            "status": self.status.value,
            "proposal_hash": self.proposal_hash,
            "human_review_ref": self.human_review_ref,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> Self:
        classification = value["classification_id"]
        evidence = value["source_evidence_ids"]
        if not isinstance(classification, list) or not isinstance(evidence, list):
            raise ValueError("invalid proposal serialization")
        expiry = value.get("expires_at")
        return cls(
            str(value["proposal_id"]),
            str(value["principal_id"]),
            str(value["tenant_id"]),
            str(value["domain_id"]),
            (str(classification[0]), str(classification[1])),
            str(value["purpose_id"]),
            str(value["proposed_operation"]),
            str(value["target_capability"]),
            str(value["target_resource"]),
            tuple(str(item) for item in evidence),
            str(value["rationale"]),
            str(value["confidence"]),
            str(value["expected_outcome"]),
            str(value["risk_level"]),
            str(value["reversibility"]),
            str(value["required_permission"]),
            str(value["required_approval"]),
            None if value.get("draft_text") is None else str(value["draft_text"]),
            datetime.fromisoformat(str(value["created_at"])),
            None if expiry is None else datetime.fromisoformat(str(expiry)),
            ActionStatus(str(value["status"])),
            str(value["proposal_hash"]),
            None
            if value.get("human_review_ref") is None
            else str(value["human_review_ref"]),
        )
