"""Intelligence Retrieval & Context Alpha public API."""

from edn.intelligence.adapters import (
    CalendarEvidenceAdapter,
    CapabilityGapAdapter,
    EmailRetrievalAdapter,
    KnowledgeGraphAdapter,
    SourceAdapter,
)
from edn.intelligence.context import ContextAssembler
from edn.intelligence.models import (
    AssembledContext,
    ContextEvidence,
    GlobalKnowledge,
    IntelligencePriority,
    IntelligenceRequest,
    IntelligenceResponse,
    IntelligenceStatement,
    StatementKind,
)
from edn.intelligence.service import IntelligenceService
from edn.intelligence.session import InMemorySessionStore, SessionState

__all__ = [
    "AssembledContext",
    "CalendarEvidenceAdapter",
    "CapabilityGapAdapter",
    "ContextAssembler",
    "ContextEvidence",
    "EmailRetrievalAdapter",
    "GlobalKnowledge",
    "InMemorySessionStore",
    "IntelligencePriority",
    "IntelligenceRequest",
    "IntelligenceResponse",
    "IntelligenceService",
    "IntelligenceStatement",
    "KnowledgeGraphAdapter",
    "SessionState",
    "SourceAdapter",
    "StatementKind",
]
