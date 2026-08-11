"""Permission-first, bounded context assembly across source-neutral adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from edn.core import PermissionRequest
from edn.core.policy import PermissionEvaluator, evaluate_capability_use
from edn.core.registry import CapabilityRegistry
from edn.intelligence.adapters import SourceAdapter
from edn.intelligence.models import (
    AssembledContext,
    ContextEvidence,
    GlobalKnowledge,
    IntelligenceRequest,
)


@dataclass(slots=True)
class ContextAssembler:
    registry: CapabilityRegistry
    policy: PermissionEvaluator
    adapters: tuple[SourceAdapter, ...]
    per_source_limit: int = 5
    total_limit: int = 10

    def assemble(
        self,
        request: IntelligenceRequest,
        *,
        now: datetime,
        global_knowledge: tuple[GlobalKnowledge, ...] = (),
    ) -> AssembledContext:
        evidence = []
        unavailable = []
        for adapter in sorted(self.adapters, key=lambda item: item.capability_id):
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
                continue
            retrieved = adapter.retrieve(
                request,
                limit=self.per_source_limit,
                now=now,
                authority=decision,
            )
            for item in retrieved:
                if any(
                    ref.record.security_domain != request.security_domain
                    or ref.record.classification != request.classification
                    for ref in item.provenance
                ):
                    unavailable.append(
                        f"{adapter.capability_id}:evidence_scope_mismatch"
                    )
                    continue
                evidence.append(item)
        # Every adapter is already bounded. Round-robin keeps one prolific source
        # from crowding all other authorised families out of the final context.
        families: dict[str, list[ContextEvidence]] = {}
        for item in sorted(
            evidence, key=lambda value: (-value.score, value.context_id)
        ):
            families.setdefault(item.source_label, []).append(item)
        balanced: list[ContextEvidence] = []
        while families and len(balanced) < self.total_limit:
            for family in sorted(tuple(families)):
                items = families[family]
                balanced.append(items.pop(0))
                if not items:
                    del families[family]
                if len(balanced) >= self.total_limit:
                    break
        deduplicated = {item.context_id: item for item in balanced}
        return AssembledContext(
            request,
            tuple(deduplicated.values())[: self.total_limit],
            tuple(sorted(set(unavailable))),
            global_knowledge,
        )
