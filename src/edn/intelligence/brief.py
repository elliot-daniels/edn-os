"""Deterministic Daily Intelligence composition over authorised context."""

from __future__ import annotations

from dataclasses import dataclass

from edn.intelligence.models import AssembledContext, IntelligencePriority


@dataclass(frozen=True, slots=True)
class DailyIntelligenceComposer:
    """Convert bounded evidence into at most ten reviewable priorities."""

    maximum_priorities: int = 10

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_priorities <= 10:
            raise ValueError("maximum priorities must be between zero and ten")

    def compose(self, context: AssembledContext) -> tuple[IntelligencePriority, ...]:
        return tuple(
            IntelligencePriority(
                title=item.title,
                why_it_matters=item.excerpt,
                evidence_ids=(item.context_id,),
                timeframe=item.provenance[0].locator,
                confidence="evidence-backed",
                recommended_next_step=_next_step(item.source_label),
                missing_information=(
                    "Current status, accountable owner, and required decision "
                    "are not established by this evidence alone.",
                ),
            )
            for item in context.evidence[: self.maximum_priorities]
        )


def _next_step(source_label: str) -> str:
    family = source_label.casefold()
    if "calendar" in family:
        return "Confirm attendance, preparation, owner, and any decision required."
    if "email" in family:
        return "Confirm the accountable owner, deadline, and response required."
    if "knowledge" in family:
        return "Validate the current state against the cited source records."
    return "Review the cited evidence and confirm the owner and next decision."
