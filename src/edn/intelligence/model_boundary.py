"""Synthetic-only model/disclosure boundary contracts.

This module deliberately contains no network or provider SDK dependency.  It
prepares a minimum projected context, records the disclosure decision, and
keeps model output epistemically separate from verified EDN evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from edn.core import Classification
from edn.intelligence.models import (
    AssembledContext,
    ContextEvidence,
    FreshnessState,
    TemporalState,
)
from edn.intelligence.temporal import temporal_state


class DisclosureOutcome(StrEnum):
    ALLOWED = "allowed"
    REDACTED_PROJECTED = "redacted_projected"
    DENIED = "denied"
    CLASSIFICATION_CEILING_EXCEEDED = "classification_ceiling_exceeded"
    UNKNOWN_CLASSIFICATION = "unknown_classification"
    MISSING_AUTHORITY = "missing_authority"


class ModelStatementKind(StrEnum):
    MODEL_ASSERTION = "model_assertion"
    UNSUPPORTED_ASSERTION = "unsupported_assertion"
    UNCERTAINTY = "uncertainty"
    EVIDENCE_GAP = "evidence_gap"
    PROPOSED_ACTION = "proposed_action"


@dataclass(frozen=True, slots=True)
class DisclosurePolicy:
    """Explicit, bounded synthetic disclosure authority."""

    authority_ref: str | None
    classification_ceiling: Classification
    allowed_domains: frozenset[str]
    max_evidence_items: int = 8
    max_context_chars: int = 4_000

    def __post_init__(self) -> None:
        if self.authority_ref is not None and not self.authority_ref.strip():
            raise ValueError("authority_ref must not be blank")
        if not self.allowed_domains:
            raise ValueError("allowed_domains must not be empty")
        if self.max_evidence_items < 1 or self.max_context_chars < 1:
            raise ValueError("disclosure limits must be positive")


@dataclass(frozen=True, slots=True)
class DisclosureDecision:
    outcome: DisclosureOutcome
    reason_code: str
    request_id: str
    evidence_ids: tuple[str, ...] = ()

    @property
    def is_allowed(self) -> bool:
        return self.outcome in {
            DisclosureOutcome.ALLOWED,
            DisclosureOutcome.REDACTED_PROJECTED,
        }


@dataclass(frozen=True, slots=True)
class ProjectedEvidence:
    """Minimum provider-visible evidence; internal IDs and raw records stay out."""

    disclosure_id: str
    source_family: str
    title: str
    excerpt: str
    freshness: FreshnessState
    provenance_digest: str
    source_timestamp: datetime | None = None
    field_category: str = "unknown"
    provider_approved: bool = False
    temporal_state: TemporalState = TemporalState.UNKNOWN_UNDETERMINED


@dataclass(frozen=True, slots=True)
class DisclosureProjection:
    request_id: str
    items: tuple[ProjectedEvidence, ...]
    total_chars: int
    redactions: tuple[str, ...] = ()
    reference_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class ModelRequest:
    request_id: str
    purpose: str
    principal_id: str
    security_domain: str
    evidence_references: tuple[str, ...]
    projection: DisclosureProjection
    classification: Classification
    capability: str
    max_output_items: int
    synthetic_fixture: bool = True
    approval_token: str | None = None


@dataclass(frozen=True, slots=True)
class ModelStatement:
    kind: ModelStatementKind
    text: str
    disclosed_evidence_ids: tuple[str, ...] = ()
    uncertainty: str | None = None
    provider_id: str = ""
    proposal_only: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("model statement text must not be blank")
        if self.kind is ModelStatementKind.PROPOSED_ACTION and not self.proposal_only:
            raise ValueError("model actions must remain proposal-only")
        if self.kind is not ModelStatementKind.PROPOSED_ACTION and self.proposal_only:
            raise ValueError("only model actions may be proposal-only")
        if (
            self.kind is ModelStatementKind.UNSUPPORTED_ASSERTION
            and self.disclosed_evidence_ids
        ):
            raise ValueError("unsupported assertions cannot cite disclosed evidence")


@dataclass(frozen=True, slots=True)
class ModelResponse:
    request_id: str
    provider_id: str
    statements: tuple[ModelStatement, ...]
    disclosed_evidence_ids: tuple[str, ...]
    fallback_required: bool = False


class ModelProvider(Protocol):
    provider_id: str

    def generate(self, request: ModelRequest) -> ModelResponse: ...


@dataclass(frozen=True, slots=True)
class BoundaryResult:
    decision: DisclosureDecision
    projection: DisclosureProjection | None
    model_response: ModelResponse | None
    fallback_available: bool
    fallback_reason: str | None = None


class DisclosureProjector:
    """Fail-closed classification/domain check followed by bounded projection."""

    def decide(
        self,
        context: AssembledContext,
        *,
        request_id: str,
        policy: DisclosurePolicy,
    ) -> DisclosureDecision:
        if policy.authority_ref is None:
            return DisclosureDecision(
                DisclosureOutcome.MISSING_AUTHORITY,
                "missing_disclosure_authority",
                request_id,
            )
        if not context.request.principal.allows_domain(context.request.security_domain):
            return DisclosureDecision(
                DisclosureOutcome.DENIED, "principal_domain_denied", request_id
            )
        if context.request.security_domain.domain_id not in policy.allowed_domains:
            return DisclosureDecision(
                DisclosureOutcome.DENIED, "domain_not_in_disclosure_scope", request_id
            )
        evidence_ids = tuple(item.context_id for item in context.evidence)
        if len(context.evidence) > policy.max_evidence_items:
            return DisclosureDecision(
                DisclosureOutcome.DENIED,
                "evidence_item_budget_exceeded",
                request_id,
                evidence_ids,
            )
        for item in context.evidence:
            for reference in item.provenance:
                classification = reference.record.classification
                if classification.rank is None:
                    return DisclosureDecision(
                        DisclosureOutcome.UNKNOWN_CLASSIFICATION,
                        "unknown_classification",
                        request_id,
                        evidence_ids,
                    )
                ceiling = policy.classification_ceiling
                if classification.scheme_id != ceiling.scheme_id:
                    return DisclosureDecision(
                        DisclosureOutcome.DENIED,
                        "classification_scheme_mismatch",
                        request_id,
                        evidence_ids,
                    )
                if ceiling.rank is None or classification.rank > ceiling.rank:
                    return DisclosureDecision(
                        DisclosureOutcome.CLASSIFICATION_CEILING_EXCEEDED,
                        "classification_ceiling_exceeded",
                        request_id,
                        evidence_ids,
                    )
                if (
                    reference.record.security_domain.domain_id
                    not in policy.allowed_domains
                ):
                    return DisclosureDecision(
                        DisclosureOutcome.DENIED,
                        "evidence_domain_not_in_scope",
                        request_id,
                        evidence_ids,
                    )
        return DisclosureDecision(
            DisclosureOutcome.ALLOWED,
            "bounded_disclosure_allowed",
            request_id,
            evidence_ids,
        )

    def project(
        self,
        context: AssembledContext,
        *,
        request_id: str,
        policy: DisclosurePolicy,
        reference_time: datetime | None = None,
    ) -> tuple[DisclosureDecision, DisclosureProjection | None]:
        decision = self.decide(context, request_id=request_id, policy=policy)
        if not decision.is_allowed:
            return decision, None
        reference = reference_time or datetime.now(UTC)
        if reference.tzinfo is None:
            raise ValueError("temporal reference time must be timezone-aware")
        remaining = policy.max_context_chars
        projected: list[ProjectedEvidence] = []
        redactions: list[str] = []
        for index, item in enumerate(
            context.evidence[: policy.max_evidence_items], start=1
        ):
            prefix = f"{item.title}: "
            available = remaining - len(prefix)
            if available <= 0:
                redactions.append(f"{item.context_id}:context_budget")
                break
            raw_excerpt = item.excerpt[:available]
            excerpt = _safe_excerpt(raw_excerpt)[:available]
            if excerpt != raw_excerpt:
                redactions.append(f"{item.context_id}:sensitive_marker")
            if len(excerpt) < len(item.excerpt):
                redactions.append(f"{item.context_id}:excerpt_truncated")
            digest = hashlib.sha256(
                "|".join(ref.evidence_id for ref in item.provenance).encode()
            ).hexdigest()[:16]
            projected.append(
                ProjectedEvidence(
                    f"disclosed-{index}",
                    item.source_label,
                    item.title,
                    excerpt,
                    _freshness(item),
                    digest,
                    item.source_timestamp,
                    temporal_state=temporal_state(item, reference),
                )
            )
            remaining -= len(prefix) + len(excerpt)
        projection = DisclosureProjection(
            request_id,
            tuple(projected),
            policy.max_context_chars - remaining,
            tuple(redactions),
            reference,
        )
        if redactions:
            decision = DisclosureDecision(
                DisclosureOutcome.REDACTED_PROJECTED,
                "minimum_projection_redacted",
                request_id,
                decision.evidence_ids,
            )
        return decision, projection


class SyntheticModelProvider:
    """Deterministic local fake provider. It refuses non-synthetic requests."""

    provider_id = "synthetic.local.fake"

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not request.synthetic_fixture:
            raise PermissionError("synthetic provider accepts synthetic fixtures only")
        if request.projection.request_id != request.request_id:
            raise ValueError("projection/request correlation mismatch")
        statements: list[ModelStatement] = []
        for item in request.projection.items[: request.max_output_items]:
            statements.append(
                ModelStatement(
                    ModelStatementKind.MODEL_ASSERTION,
                    f"Model-assisted synthesis: {item.title} requires owner review.",
                    (item.disclosure_id,),
                    uncertainty="inference from projected evidence",
                    provider_id=self.provider_id,
                )
            )
        if not request.projection.items:
            statements.append(
                ModelStatement(
                    ModelStatementKind.EVIDENCE_GAP,
                    "No evidence was disclosed; conclusion is unavailable.",
                    provider_id=self.provider_id,
                )
            )
        statements.append(
            ModelStatement(
                ModelStatementKind.PROPOSED_ACTION,
                "Consider confirming owners and next decisions.",
                tuple(item.disclosure_id for item in request.projection.items[:1]),
                uncertainty="proposal only",
                provider_id=self.provider_id,
                proposal_only=True,
            )
        )
        return ModelResponse(
            request.request_id,
            self.provider_id,
            tuple(statements),
            tuple(item.disclosure_id for item in request.projection.items),
        )


class ModelIntelligenceBoundary:
    """Orchestrates disclosure and local provider use without changing authority."""

    def __init__(
        self,
        provider: ModelProvider | None = None,
        projector: DisclosureProjector | None = None,
    ) -> None:
        self.provider = provider or SyntheticModelProvider()
        self.projector = projector or DisclosureProjector()

    def run(
        self,
        context: AssembledContext,
        *,
        policy: DisclosurePolicy,
        request_id: str,
        capability: str = "model.summarize",
        max_output_items: int = 5,
        reference_time: datetime | None = None,
    ) -> BoundaryResult:
        decision, projection = self.projector.project(
            context,
            request_id=request_id,
            policy=policy,
            reference_time=reference_time,
        )
        if projection is None:
            return BoundaryResult(decision, None, None, True, decision.reason_code)
        request = ModelRequest(
            request_id,
            context.request.purpose.purpose_id,
            context.request.principal.principal_id,
            context.request.security_domain.domain_id,
            tuple(item.disclosure_id for item in projection.items),
            projection,
            context.request.classification,
            capability,
            max_output_items,
        )
        try:
            response = self.provider.generate(request)
        except (PermissionError, ValueError, RuntimeError) as exc:
            return BoundaryResult(
                decision, projection, None, True, type(exc).__name__.casefold()
            )
        return BoundaryResult(decision, projection, response, True)


def _freshness(item: ContextEvidence) -> FreshnessState:
    # The source-specific Daily Brief policy declares this state. Never infer
    # currentness from retrieval order or from the mere presence of a timestamp.
    return item.freshness_state


_SENSITIVE_MARKER = re.compile(
    r"(?i)(?:secret|token|password|access_token|raw_graph_payload)\s*[=:]\s*[^\s,;]+"
)


def _safe_excerpt(value: str) -> str:
    """Remove obvious synthetic secret/payload markers before provider exposure."""
    return _SENSITIVE_MARKER.sub("[redacted]", value)
