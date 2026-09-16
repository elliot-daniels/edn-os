"""Offline fixture host for the real morning application. No network client exists.

Run: python -m edn.intelligence.synthetic_morning FIXTURE STATE_DIRECTORY
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from edn.connectors.errors import SourceUnavailableError
from edn.core import (
    CapabilityManifest,
    CapabilityUseDecision,
    Classification,
    EvidenceRef,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    SourceRef,
    UniversalRecordRef,
)
from edn.core.capabilities import CapabilityStatus
from edn.core.permissions import PermissionOutcome
from edn.core.policy import PermissionEvaluator, PolicyRule, PolicySet
from edn.core.registry import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
)
from edn.intelligence.models import (
    BusinessFacts,
    ContextEvidence,
    IntelligenceRequest,
    SourceBatch,
)
from edn.intelligence.morning import MorningBriefApplication, MorningSourceConfiguration
from edn.intelligence.operations import DailySchedule


@dataclass(slots=True)
class SyntheticMorningSource:
    capability_id: str
    source_instance_id: str
    records: tuple[dict[str, Any], ...]
    unavailable: bool = False
    freshness: str = "checked"
    operation: str = "evidence.retrieve"

    @property
    def resource_scope(self) -> tuple[str, ...]:
        return (self.source_instance_id,)

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> SourceBatch:
        if not authority.is_usable:
            raise PermissionError("synthetic source requires policy authority")
        if self.unavailable:
            raise SourceUnavailableError("Synthetic unavailable source")
        evidence = []
        for raw in self.records[:limit]:
            identity = str(raw["id"])
            source = SourceRef(
                "synthetic-morning",
                "synthetic",
                self.source_instance_id,
                "Synthetic morning fixture",
            )
            record = UniversalRecordRef(
                source,
                identity,
                request.security_domain,
                request.classification,
                "synthetic-record",
            )
            timestamp = _datetime(raw.get("timestamp"))
            business = raw.get("business")
            facts = (
                None
                if business is None
                else BusinessFacts(
                    business["kind"],
                    identity,
                    business.get("status", ""),
                    date.fromisoformat(business["due"])
                    if business.get("due")
                    else None,
                    business.get("project", ""),
                    business.get("client", ""),
                    business.get("owner", ""),
                )
            )
            evidence.append(
                ContextEvidence(
                    f"synthetic:{self.source_instance_id}:{identity}",
                    self.capability_id,
                    "Synthetic " + self.source_instance_id,
                    str(raw["title"]),
                    str(raw["text"]),
                    1.0,
                    (
                        EvidenceRef(
                            f"fixture:{self.source_instance_id}:{identity}",
                            record,
                            locator="synthetic fixture",
                        ),
                    ),
                    timestamp,
                    raw.get("timestamp_kind") if timestamp else None,
                    temporal_start=_datetime(raw.get("start")),
                    temporal_end=_datetime(raw.get("end")),
                    source_instance_id=self.source_instance_id,
                    business_facts=facts,
                )
            )
        reasons: tuple[str, ...] = ("synthetic_fixture",)
        if self.freshness != "checked":
            reasons += ("local_corpus_may_be_stale",)
        return SourceBatch(
            tuple(evidence),
            len(self.records),
            now,
            len(self.records) > limit,
            reasons,
            self.freshness,
        )


def _datetime(value: object) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))


def application(
    fixture: Path, state_directory: Path
) -> tuple[MorningBriefApplication, datetime]:
    data = json.loads(fixture.read_text(encoding="utf-8"))
    if data.get("mode") != "synthetic-only":
        raise ValueError("this host accepts synthetic-only fixtures")
    now = datetime.fromisoformat(data["now"])
    domain = SecurityDomain("EDN", "Synthetic EDN", tenant_id="synthetic-tenant")
    classification = Classification("synthetic", "internal", "Synthetic only", 1)
    request = IntelligenceRequest(
        "Morning brief",
        PrincipalContext(
            "synthetic-owner", "synthetic-tenant", frozenset({domain}), True
        ),
        Purpose("morning-brief", "Offline morning demonstration"),
        domain,
        classification,
    )
    adapters = tuple(
        SyntheticMorningSource(
            source["capability"],
            source["instance"],
            tuple(source.get("records", [])),
            source.get("unavailable", False),
            source.get("freshness", "checked"),
        )
        for source in data["sources"]
    )
    registry = CapabilityRegistry()
    for capability in sorted({source.capability_id for source in adapters}):
        registry.register(
            CapabilityManifest(
                capability,
                "offline-fixture",
                "synthetic",
                "1",
                frozenset({"evidence.retrieve"}),
                frozenset(),
                frozenset({domain.domain_id}),
                "read",
            ),
            CapabilityRuntimeState(
                CapabilityStatus.READY, AuthenticationStatus.NOT_REQUIRED
            ),
        )
    policy = PermissionEvaluator(
        PolicySet(
            "synthetic-morning",
            "1",
            tuple(
                PolicyRule(
                    f"source-{index}",
                    PermissionOutcome.ALLOWED_WITHIN_SCOPE,
                    "Synthetic fixture only; no Microsoft authority.",
                    principal_ids=frozenset({"synthetic-owner"}),
                    tenant_ids=frozenset({"synthetic-tenant"}),
                    domain_ids=frozenset({"EDN"}),
                    capability_ids=frozenset({source.capability_id}),
                    operations=frozenset({"evidence.retrieve"}),
                    resource_scopes=frozenset(source.resource_scope),
                )
                for index, source in enumerate(adapters)
            ),
        )
    )
    return MorningBriefApplication(
        sources=MorningSourceConfiguration(adapters),
        registry=registry,
        policy=policy,
        request=request,
        state_directory=state_directory,
        schedule=DailySchedule(timezone="Australia/Sydney", next_expected_run=now),
    ), now


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("state_directory", type=Path)
    args = parser.parse_args()
    app, now = application(args.fixture, args.state_directory)
    run = app.tick(now=now)
    print(json.dumps(None if run is None else run.to_dict(), indent=2))


if __name__ == "__main__":
    main()
