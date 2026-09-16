"""Permission-first, bounded context assembly across source-neutral adapters."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from math import isfinite

from edn.connectors.errors import ConnectorError
from edn.core import PermissionRequest
from edn.core.policy import PermissionEvaluator, evaluate_capability_use
from edn.core.registry import CapabilityRegistry
from edn.intelligence.adapters import SourceAdapter
from edn.intelligence.models import (
    AssembledContext,
    ContextEvidence,
    GlobalKnowledge,
    IntelligenceRequest,
    SourceBatch,
    SourceCoverage,
)


@dataclass(slots=True)
class ContextAssembler:
    registry: CapabilityRegistry
    policy: PermissionEvaluator
    adapters: tuple[SourceAdapter, ...]
    per_source_limit: int = 5
    total_limit: int = 10

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not 1 <= self.per_source_limit <= 25 or not 1 <= self.total_limit <= 100:
            raise ValueError("context limits must be positive and bounded")
        ids = [(adapter.capability_id, _instance(adapter)) for adapter in self.adapters]
        if len(set(ids)) != len(ids):
            raise ValueError(
                "context adapters must have unique capability/instance IDs"
            )

    def assemble(
        self,
        request: IntelligenceRequest,
        *,
        now: datetime,
        global_knowledge: tuple[GlobalKnowledge, ...] = (),
    ) -> AssembledContext:
        self._validate()
        if now.tzinfo is None:
            raise ValueError("context reference time must be timezone-aware")
        evidence = []
        unavailable = []
        coverage = []
        for adapter in sorted(
            self.adapters, key=lambda item: (item.capability_id, _instance(item))
        ):
            instance = _instance(adapter)
            permission_request = PermissionRequest(
                f"context:{adapter.capability_id}",
                request.principal,
                request.purpose,
                adapter.capability_id,
                adapter.operation,
                request.security_domain,
                request.classification,
                adapter.resource_scope,
            )
            decision = evaluate_capability_use(
                self.registry, self.policy, permission_request, now=now
            )
            if not decision.is_usable:
                unavailable.append(f"{adapter.capability_id}:{decision.reason_code}")
                coverage.append(
                    SourceCoverage(
                        adapter.capability_id,
                        "unavailable",
                        reasons=(decision.reason_code,),
                        source_instance_id=instance,
                    )
                )
                continue
            try:
                result = adapter.retrieve(
                    request,
                    limit=self.per_source_limit,
                    now=now,
                    authority=decision,
                )
            except ConnectorError:
                # Never copy transport messages, URLs or credentials into a brief.
                # Programming errors still propagate to the existing run lifecycle.
                unavailable.append(f"{adapter.capability_id}:connector_failure")
                coverage.append(
                    SourceCoverage(
                        adapter.capability_id,
                        "unavailable",
                        reasons=("connector_failure",),
                        source_instance_id=instance,
                    )
                )
                continue
            reasons: set[str] = set()
            batch = result if isinstance(result, SourceBatch) else None
            retrieved = result.evidence if isinstance(result, SourceBatch) else result
            if batch is not None:
                reasons.update(batch.reasons)
                if batch.truncated:
                    reasons.add("source_truncated")
                if batch.pre_filter_count > len(retrieved):
                    reasons.add("source_records_filtered")
            if len(retrieved) >= self.per_source_limit:
                reasons.add("source_limit_reached")
            admitted = 0
            seen: dict[str, ContextEvidence] = {}
            conflicts: set[str] = set()
            for item in retrieved[: self.per_source_limit]:
                if item.source_instance_id and item.source_instance_id != instance:
                    reasons.add("evidence_instance_mismatch")
                    continue
                item = replace(item, source_instance_id=instance)
                if item.capability_id != adapter.capability_id:
                    reasons.add("evidence_capability_mismatch")
                    continue
                if not isfinite(item.score):
                    reasons.add("invalid_evidence_score")
                    continue
                if any(
                    ref.record.security_domain != request.security_domain
                    or ref.record.classification != request.classification
                    for ref in item.provenance
                ):
                    reasons.add("evidence_scope_mismatch")
                    continue
                if item.context_id in seen and seen[item.context_id] != item:
                    conflicts.add(item.context_id)
                    reasons.add("conflicting_evidence_id")
                else:
                    seen[item.context_id] = item
            for key, item in seen.items():
                if key not in conflicts:
                    evidence.append(item)
                    admitted += 1
            unavailable.extend(
                f"{adapter.capability_id}:{reason}" for reason in reasons
            )
            coverage.append(
                SourceCoverage(
                    adapter.capability_id,
                    "partial" if reasons else "retrieved" if admitted else "empty",
                    len(retrieved),
                    admitted,
                    reasons=tuple(sorted(reasons)),
                    source_instance_id=instance,
                    pre_filter_count=batch.pre_filter_count if batch else None,
                    checked_at=batch.checked_at if batch else None,
                    freshness=batch.freshness if batch else "unknown",
                )
            )
        # A citation ID cannot identify two different source records. Reject both
        # rather than silently replacing one source's evidence with another's.
        by_id: dict[str, list[ContextEvidence]] = {}
        for item in evidence:
            by_id.setdefault(item.context_id, []).append(item)
        collisions = {key for key, items in by_id.items() if len(items) > 1}
        for index, source in enumerate(coverage):
            removed = sum(
                item.capability_id == source.capability_id
                and item.source_instance_id == source.source_instance_id
                and item.context_id in collisions
                for item in evidence
            )
            if removed:
                reason = "conflicting_evidence_id"
                unavailable.append(f"{source.capability_id}:{reason}")
                coverage[index] = replace(
                    source,
                    status="partial",
                    admitted_count=source.admitted_count - removed,
                    reasons=tuple(sorted(set(source.reasons) | {reason})),
                )
        evidence = [item for item in evidence if item.context_id not in collisions]
        # Every adapter is already bounded. Round-robin keeps one prolific source
        # from crowding all other authorised families out of the final context.
        families: dict[tuple[str, str], list[ContextEvidence]] = {}
        for item in sorted(
            evidence, key=lambda value: (-value.score, value.context_id)
        ):
            families.setdefault(
                (item.capability_id, item.source_instance_id), []
            ).append(item)
        balanced: list[ContextEvidence] = []
        while families and len(balanced) < self.total_limit:
            for family in sorted(tuple(families)):
                items = families[family]
                balanced.append(items.pop(0))
                if not items:
                    del families[family]
                if len(balanced) >= self.total_limit:
                    break
        for index, source in enumerate(coverage):
            selected = sum(
                item.capability_id == source.capability_id
                and item.source_instance_id == source.source_instance_id
                for item in balanced
            )
            selection_reasons = source.reasons
            if selected < source.admitted_count:
                selection_reasons = tuple(
                    sorted(set(selection_reasons) | {"context_limit_reached"})
                )
            coverage[index] = replace(
                source,
                selected_count=selected,
                reasons=selection_reasons,
                status="partial"
                if selection_reasons and source.status != "unavailable"
                else source.status,
            )
        return AssembledContext(
            request,
            tuple(balanced),
            tuple(sorted(set(unavailable))),
            global_knowledge,
            tuple(coverage),
        )


def _instance(adapter: SourceAdapter) -> str:
    value = getattr(adapter, "source_instance_id", "")
    if not isinstance(value, str):
        raise ValueError("source instance identity must be text")
    return value
