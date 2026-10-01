"""Application wiring for a local, explicitly invoked morning briefing tick.

No worker, timer, credentials, provider calls or external actions are installed.
The host injects configured adapters and its existing registry/policy authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from edn.core.policy import PermissionEvaluator
from edn.core.registry import CapabilityRegistry
from edn.intelligence.adapters import SourceAdapter
from edn.intelligence.brief import DailyIntelligenceComposer
from edn.intelligence.context import ContextAssembler
from edn.intelligence.models import IntelligenceRequest, IntelligenceResponse
from edn.intelligence.operations import (
    BriefRunResult,
    DailyIntelligenceScheduler,
    DailyOperationsStore,
    DailyRun,
    DailySchedule,
)
from edn.intelligence.service import IntelligenceService


@dataclass(frozen=True, slots=True)
class MorningSourceConfiguration:
    adapters: tuple[SourceAdapter, ...]
    per_source_limit: int = 10
    total_limit: int = 40
    timezone: str = "Australia/Sydney"


class MorningBriefApplication:
    def __init__(
        self,
        *,
        sources: MorningSourceConfiguration,
        registry: CapabilityRegistry,
        policy: PermissionEvaluator,
        request: IntelligenceRequest,
        state_directory: Path,
        schedule: DailySchedule | None = None,
    ) -> None:
        self.request = request
        self.state_directory = state_directory
        if schedule is not None and schedule.timezone != sources.timezone:
            raise ValueError(
                "schedule and source date interpretation must share a timezone"
            )
        self.service = IntelligenceService(
            ContextAssembler(
                registry,
                policy,
                sources.adapters,
                sources.per_source_limit,
                sources.total_limit,
            ),
            brief_composer=DailyIntelligenceComposer(
                deadline_priorities_only=True,
                timezone=sources.timezone,
                expected_capabilities=tuple(
                    sorted({a.capability_id for a in sources.adapters})
                ),
            ),
        )
        self.scheduler = DailyIntelligenceScheduler(
            DailyOperationsStore(state_directory / "daily-operations.db"),
            schedule or DailySchedule(timezone=sources.timezone),
        )

    def tick(self, *, now: datetime) -> DailyRun | None:
        return self.scheduler.tick(now=now, runner=lambda: self._generate(now))

    def retry(self, run_id: str, *, now: datetime) -> DailyRun:
        return self.scheduler.retry(run_id, now=now, runner=lambda: self._generate(now))

    def _generate(self, now: datetime) -> BriefRunResult:
        response = self.service.daily_brief(self.request, now=now)
        assert response.daily_brief is not None
        payload = {
            "schema_version": 1,
            "generated_at": now.isoformat(),
            "brief": asdict(response.daily_brief),
            "coverage": [asdict(source) for source in response.source_coverage],
            "evidence": [asdict(item) for item in response.evidence],
            "markdown": render_brief(response),
        }
        content = json.dumps(payload, default=str, sort_keys=True, indent=2).encode()
        digest = hashlib.sha256(content).hexdigest()
        destination = self.state_directory / f"brief-{digest}.json"
        self.state_directory.mkdir(parents=True, exist_ok=True)
        temporary = self.state_directory / f".brief-{uuid4().hex}.tmp"
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return BriefRunResult.from_brief(
            response.daily_brief, str(destination.resolve())
        )


def render_brief(response: IntelligenceResponse) -> str:
    """Render only typed service output, retaining resolvable source citations."""
    brief = response.daily_brief
    if brief is None:
        raise ValueError("daily brief required")
    lines = [
        "# Good morning",
        "",
        f"Brief generated at {brief.generated_at.isoformat()}.",
        "",
    ]
    if any(
        ref.record.source.connector_id == "synthetic"
        for evidence in response.evidence
        for ref in evidence.provenance
    ):
        lines.extend(("**Synthetic demonstration — no live-source validation.**", ""))
    for section in brief.sections:
        if not section.items:
            continue
        lines.extend((f"## {section.title}", ""))
        for item in section.items:
            refs = " ".join(f"[{identity}]" for identity in item.evidence_ids)
            lines.append(
                f"- **{item.title}** ({item.kind.value}): {item.text} {refs}".rstrip()
            )
        lines.append("")
    lines.extend(("## Coverage", ""))
    for source in response.source_coverage:
        lines.append(
            f"- {source.capability_id} / {source.source_instance_id or 'default'}: "
            f"{source.status}; {source.selected_count}/{source.returned_count} "
            "included; "
            f"pre-filter={source.pre_filter_count}; freshness={source.freshness}; "
            f"checked={source.checked_at}; "
            f"reasons={', '.join(source.reasons) or 'none'}."
        )
    lines.extend(("", "## Evidence", ""))
    decisions = [
        d for source in response.source_coverage for d in source.admission_decisions
    ]
    if decisions:
        lines[-2:] = ["## Admission audit", ""]
        for decision in decisions:
            lines.append(
                f"- {decision.record_key}: {decision.outcome.value}; "
                f"reasons={', '.join(decision.reasons)}; policy={decision.policy_id}."
            )
        lines.extend(("", "## Evidence", ""))
    for evidence in response.evidence:
        for ref in evidence.provenance:
            lines.append(
                f"- [{evidence.context_id}]: {ref.record.source.source_instance_id} / "
                f"{ref.record.source_record_key}; {ref.locator}"
            )
    return "\n".join(lines) + "\n"
