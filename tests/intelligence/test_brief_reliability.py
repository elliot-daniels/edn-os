"""Source failures, bounded admission and temporal briefing regressions."""

from dataclasses import replace
from datetime import timedelta

import pytest
from tests.intelligence.test_context_alpha import (
    NOW,
    FakeAdapter,
    _assembler,
    _evidence,
    _request,
)

from edn.connectors.errors import AuthenticationRequiredError, TransientConnectorError
from edn.intelligence import (
    AssembledContext,
    BriefSectionKind,
    DailyIntelligenceComposer,
    FreshnessState,
    IntelligenceService,
    SourceCoverage,
    StatementKind,
)


class ReturningAdapter(FakeAdapter):
    def __init__(self, capability_id, records=(), error=None):
        super().__init__(capability_id, capability_id)
        self.records = records
        self.error = error

    def retrieve(self, request, *, limit, now, authority):
        self.calls.append(request.security_domain.domain_id)
        if self.error is not None:
            raise self.error
        return self.records


@pytest.mark.parametrize(
    "error_type", [TransientConnectorError, AuthenticationRequiredError]
)
def test_failed_source_leaves_other_evidence_and_safe_gap(error_type):
    failed = ReturningAdapter(
        "calendar.search", error=error_type("secret-token=PRIVATE")
    )
    healthy = FakeAdapter("email.retrieve", "mail")
    response = IntelligenceService(_assembler((failed, healthy))).daily_brief(
        _request(), now=NOW
    )
    assert len(response.evidence) == 1
    assert response.source_coverage[0].status == "unavailable"
    assert response.source_coverage[1].selected_count == 1
    assert "PRIVATE" not in repr(response)
    assert "calendar.search:connector_failure" in response.unavailable_capabilities
    gap = next(
        x for x in response.daily_brief.items if x.item_id == "coverage:calendar.search"
    )
    assert gap.kind is StatementKind.UNKNOWN
    assert failed.calls == ["EDN"]  # no autonomous retry or credential refresh


def test_programming_errors_are_not_disguised_as_source_outages():
    adapter = ReturningAdapter("calendar.search", error=RuntimeError("broken code"))
    with pytest.raises(RuntimeError, match="broken code"):
        _assembler((adapter,)).assemble(_request(), now=NOW)


def test_denied_source_is_not_called_even_if_it_would_fail():
    denied = ReturningAdapter("calendar.search", error=AssertionError("must not run"))
    assembler = _assembler(
        (denied, FakeAdapter("email.retrieve", "mail")),
        allowed=frozenset({"email.retrieve"}),
    )
    context = assembler.assemble(_request(), now=NOW)
    assert denied.calls == []
    assert context.source_coverage[0].status == "unavailable"


def test_empty_success_is_distinct_from_unavailable_and_never_all_clear():
    response = IntelligenceService(
        _assembler((ReturningAdapter("calendar.search"),))
    ).daily_brief(_request(), now=NOW)
    assert response.source_coverage[0] == SourceCoverage("calendar.search", "empty")
    assert response.unavailable_capabilities == ()
    assert any(
        "No matching evidence does not establish" in x.text
        for x in response.daily_brief.items
    )


def test_adapter_limit_is_enforced_and_partial_evidence_is_visible():
    records = tuple(_evidence(_request(), "email.retrieve", str(i)) for i in range(8))
    assembler = _assembler((ReturningAdapter("email.retrieve", records),))
    context = assembler.assemble(_request(), now=NOW)
    assert len(context.evidence) == 5
    assert context.source_coverage[0] == SourceCoverage(
        "email.retrieve", "partial", 8, 5, 5, ("source_limit_reached",)
    )
    brief = DailyIntelligenceComposer().compose(context, now=NOW)
    assert any(x.item_id == "coverage:email.retrieve" for x in brief.items)


def test_context_limit_reports_admitted_but_omitted_source_items():
    assembler = _assembler((FakeAdapter("email.retrieve", "mail", count=3),))
    assembler.total_limit = 1
    context = assembler.assemble(_request(), now=NOW)
    assert context.source_coverage[0] == SourceCoverage(
        "email.retrieve", "partial", 3, 3, 1, ("context_limit_reached",)
    )


def test_exact_duplicates_do_not_consume_other_evidence_slots():
    first = _evidence(_request(), "email.retrieve", "first")
    second = _evidence(_request(), "email.retrieve", "second")
    context = _assembler(
        (ReturningAdapter("email.retrieve", (first, first, second)),)
    ).assemble(_request(), now=NOW)
    assert context.evidence == (first, second)
    assert context.source_coverage[0].admitted_count == 2


def test_conflicting_citation_ids_are_rejected_without_order_based_overwrite():
    first = _evidence(_request(), "email.retrieve", "same")
    conflict = replace(first, excerpt="Different fact")
    for records in ((first, conflict), (conflict, first)):
        context = _assembler((ReturningAdapter("email.retrieve", records),)).assemble(
            _request(), now=NOW
        )
        assert context.evidence == ()
        assert context.source_coverage[0].reasons == ("conflicting_evidence_id",)


def test_cross_capability_citation_collision_rejects_both_sources():
    first = _evidence(_request(), "email.retrieve", "same")
    second = replace(first, capability_id="knowledge.retrieve")
    context = _assembler(
        (
            ReturningAdapter("email.retrieve", (first,)),
            ReturningAdapter("knowledge.retrieve", (second,)),
        )
    ).assemble(_request(), now=NOW)
    assert context.evidence == ()
    assert all(x.admitted_count == 0 for x in context.source_coverage)
    assert all(x.status == "partial" for x in context.source_coverage)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_ranking_scores_are_not_admitted(score):
    record = replace(_evidence(_request(), "email.retrieve", "one"), score=score)
    context = _assembler((ReturningAdapter("email.retrieve", (record,)),)).assemble(
        _request(), now=NOW
    )
    assert context.evidence == ()
    assert context.source_coverage[0].reasons == ("invalid_evidence_score",)


def test_adapter_cannot_misattribute_evidence_to_another_capability():
    record = _evidence(_request(), "calendar.search", "one")
    context = _assembler((ReturningAdapter("email.retrieve", (record,)),)).assemble(
        _request(), now=NOW
    )
    assert context.evidence == ()
    assert context.source_coverage[0].reasons == ("evidence_capability_mismatch",)


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_limit", 0),
        ("total_limit", 101),
        ("per_source_limit", 0),
        ("per_source_limit", 26),
    ],
)
def test_changed_invalid_bounds_fail_before_retrieval(field, value):
    adapter = FakeAdapter("email.retrieve", "mail")
    assembler = _assembler((adapter,))
    setattr(assembler, field, value)
    with pytest.raises(ValueError, match="limits"):
        assembler.assemble(_request(), now=NOW)
    assert adapter.calls == []


def _calendar(start, end):
    return replace(
        _evidence(_request(), "calendar.search", "meeting"),
        source_timestamp=end,
        timestamp_kind="calendar_event_end",
        temporal_start=start,
        temporal_end=end,
    )


def test_recently_ended_meeting_is_historical_not_an_upcoming_priority():
    record = _calendar(NOW - timedelta(hours=2), NOW - timedelta(minutes=1))
    context = AssembledContext(_request(), (record,), ())
    composer = DailyIntelligenceComposer()
    brief = composer.compose(context, now=NOW)
    assert composer.priorities(brief) == ()
    facts = [x for x in brief.items if x.kind is StatementKind.FACT]
    assert facts[0].section is BriefSectionKind.RISKS_GAPS
    assert facts[0].freshness is FreshnessState.STALE
    assert not any(
        x.section is BriefSectionKind.IMMEDIATE_ATTENTION for x in brief.items
    )


@pytest.mark.parametrize(
    "start,end",
    [
        (NOW, NOW + timedelta(hours=1)),
        (NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
    ],
)
def test_current_and_upcoming_calendar_evidence_retains_priority(start, end):
    brief = DailyIntelligenceComposer().compose(
        AssembledContext(_request(), (_calendar(start, end),), ()), now=NOW
    )
    assert any(x.section is BriefSectionKind.UPCOMING_COMMITMENTS for x in brief.items)
    assert any(x.section is BriefSectionKind.IMMEDIATE_ATTENTION for x in brief.items)


def test_calendar_without_event_boundaries_cannot_claim_upcoming_status():
    record = replace(
        _calendar(NOW, NOW + timedelta(hours=1)), temporal_start=None, temporal_end=None
    )
    brief = DailyIntelligenceComposer().compose(
        AssembledContext(_request(), (record,), ()), now=NOW
    )
    assert not any(
        x.section is BriefSectionKind.UPCOMING_COMMITMENTS for x in brief.items
    )


def test_future_mail_timestamp_cannot_claim_current_state():
    record = replace(
        _evidence(_request(), "outlook.search", "mail"),
        source_timestamp=NOW + timedelta(days=1),
        timestamp_kind="mail_received_at",
    )
    brief = DailyIntelligenceComposer().compose(
        AssembledContext(_request(), (record,), ()), now=NOW
    )
    assert not any(
        x.section is BriefSectionKind.IMMEDIATE_ATTENTION for x in brief.items
    )
