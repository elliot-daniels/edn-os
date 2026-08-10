"""Adapters that preserve existing retrieval implementations behind Core contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from edn.core import EvidenceRef, SourceRef, UniversalRecordRef
from edn.intelligence.models import ContextEvidence, IntelligenceRequest
from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.retrieval import RetrievalEngine


class SourceAdapter(Protocol):
    capability_id: str
    operation: str

    def retrieve(
        self, request: IntelligenceRequest, *, limit: int
    ) -> tuple[ContextEvidence, ...]: ...


def _email_ref(
    request: IntelligenceRequest, source_key: str, evidence_id: str
) -> EvidenceRef:
    source = SourceRef("email-memory", "memory", "local-email", "EDN email memory")
    record = UniversalRecordRef(
        source,
        source_key,
        request.security_domain,
        request.classification,
        "email",
        source_uri=f"edn-email:{source_key}",
    )
    return EvidenceRef(evidence_id, record, locator="retrieved email excerpt")


@dataclass(slots=True)
class EmailRetrievalAdapter:
    engine: RetrievalEngine
    capability_id: str = "email.retrieve"
    operation: str = "evidence.retrieve"

    def retrieve(
        self, request: IntelligenceRequest, *, limit: int
    ) -> tuple[ContextEvidence, ...]:
        evidence = self.engine.retrieve(request.query, limit=limit)
        return tuple(
            ContextEvidence(
                context_id=f"email:{item.evidence_id}",
                capability_id=self.capability_id,
                source_label="Email memory",
                title=item.subject or "Email",
                excerpt=item.body_excerpt,
                score=float(limit - index),
                provenance=(
                    _email_ref(
                        request,
                        item.source_record_key,
                        f"email-{item.evidence_id}",
                    ),
                ),
            )
            for index, item in enumerate(evidence)
        )


@dataclass(slots=True)
class KnowledgeGraphAdapter:
    store: KnowledgeGraphStore
    capability_id: str = "knowledge.retrieve"
    operation: str = "evidence.retrieve"

    def retrieve(
        self, request: IntelligenceRequest, *, limit: int
    ) -> tuple[ContextEvidence, ...]:
        entities = self.store.lookup_entities(request.query, limit=limit)
        items: list[ContextEvidence] = []
        for entity in entities:
            details = self.store.entity_details(entity.entity_id)
            if details is None or not details.source_record_keys:
                continue
            refs = tuple(
                _email_ref(request, key, f"kg-{entity.entity_id}-{index}")
                for index, key in enumerate(details.source_record_keys[:10], start=1)
            )
            relationships = ", ".join(
                f"{item.predicate} {item.entity.canonical_name}"
                for item in details.related_entities[:5]
            )
            excerpt = (
                f"{entity.entity_type.value}: {entity.canonical_name}; "
                f"supported by {entity.source_count} email(s)"
            )
            if relationships:
                excerpt += f"; related: {relationships}"
            items.append(
                ContextEvidence(
                    context_id=f"knowledge:{entity.entity_id}",
                    capability_id=self.capability_id,
                    source_label="Knowledge graph",
                    title=entity.canonical_name,
                    excerpt=excerpt,
                    score=float(entity.source_count),
                    provenance=refs,
                )
            )
        return tuple(items)
