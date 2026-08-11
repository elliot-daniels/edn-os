"""Deterministic Alpha response composition with explicit epistemic labels."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import uuid4

from edn.intelligence.brief import DailyIntelligenceComposer
from edn.intelligence.context import ContextAssembler
from edn.intelligence.models import (
    GlobalKnowledge,
    IntelligenceRequest,
    IntelligenceResponse,
    IntelligenceStatement,
    StatementKind,
)
from edn.intelligence.session import InMemorySessionStore, SessionState


class IntelligenceService:
    def __init__(
        self,
        assembler: ContextAssembler,
        sessions: InMemorySessionStore | None = None,
        brief_composer: DailyIntelligenceComposer | None = None,
    ) -> None:
        self._assembler = assembler
        self._sessions = sessions or InMemorySessionStore()
        self._brief_composer = brief_composer or DailyIntelligenceComposer()

    def daily_brief(
        self,
        request: IntelligenceRequest,
        *,
        now: datetime,
        session_id: str | None = None,
    ) -> IntelligenceResponse:
        """Build the user-invoked brief without widening request authority."""
        return self.answer(
            replace(request, query="What do I need to know today?"),
            now=now,
            session_id=session_id,
        )

    def answer(
        self,
        request: IntelligenceRequest,
        *,
        now: datetime,
        global_knowledge: tuple[GlobalKnowledge, ...] = (),
        session_id: str | None = None,
    ) -> IntelligenceResponse:
        if session_id is not None:
            self._sessions.require_authorized(session_id, request)
        context = self._assembler.assemble(
            request, now=now, global_knowledge=global_knowledge
        )
        actual_session_id = session_id or f"session-{uuid4().hex}"
        statements = []
        for item in context.evidence[:5]:
            statements.append(
                IntelligenceStatement(
                    StatementKind.FACT,
                    item.excerpt,
                    (item.context_id,),
                    confidence="evidence-backed",
                )
            )
        if context.evidence:
            statements.append(
                IntelligenceStatement(
                    StatementKind.RECOMMENDATION,
                    "Review the cited items together and confirm owners, deadlines, "
                    "and unresolved decisions for this week.",
                    tuple(item.context_id for item in context.evidence[:5]),
                    tuple(item.knowledge_id for item in global_knowledge),
                    confidence="bounded recommendation",
                )
            )
        else:
            statements.append(
                IntelligenceStatement(
                    StatementKind.UNKNOWN,
                    "The authorised sources did not provide enough evidence to answer.",
                )
            )
        self._sessions.save(SessionState.from_context(actual_session_id, context))
        priorities = self._brief_composer.compose(context)
        return IntelligenceResponse(
            tuple(statements),
            context.evidence,
            context.global_knowledge,
            context.unavailable_capabilities,
            actual_session_id,
            priorities,
        )
