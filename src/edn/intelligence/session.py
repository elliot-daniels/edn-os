"""Bounded Alpha session references that cannot widen authority on follow-up."""

from __future__ import annotations

from dataclasses import dataclass

from edn.intelligence.models import AssembledContext, IntelligenceRequest


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: str
    principal_id: str
    purpose_id: str
    domain_id: str
    classification_id: tuple[str, str]
    evidence_ids: tuple[str, ...]

    @classmethod
    def from_context(cls, session_id: str, context: AssembledContext) -> SessionState:
        request = context.request
        return cls(
            session_id,
            request.principal.principal_id,
            request.purpose.purpose_id,
            request.security_domain.domain_id,
            (request.classification.scheme_id, request.classification.level_id),
            tuple(item.context_id for item in context.evidence),
        )

    def authorizes(self, request: IntelligenceRequest) -> bool:
        return (
            self.principal_id == request.principal.principal_id
            and self.purpose_id == request.purpose.purpose_id
            and self.domain_id == request.security_domain.domain_id
            and self.classification_id
            == (request.classification.scheme_id, request.classification.level_id)
        )


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    def require_authorized(
        self, session_id: str, request: IntelligenceRequest
    ) -> SessionState:
        state = self._sessions.get(session_id)
        if state is None or not state.authorizes(request):
            raise PermissionError("follow-up requires the original authority boundary")
        return state
