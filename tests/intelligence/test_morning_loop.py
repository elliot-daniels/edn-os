"""Offline behavioural proof of the actual service/scheduler morning loop."""

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from tests.intelligence.test_context_alpha import NOW, _assembler, _request
from tests.intelligence.test_recent_email_brief import _record

from edn.intelligence import EmailRetrievalAdapter, IntelligenceService
from edn.intelligence.models import BriefSectionKind
from edn.intelligence.morning_sources import EmailCorpusAdapter
from edn.intelligence.operations import BriefRunResult, RunStatus
from edn.intelligence.synthetic_morning import application
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import RetrievalEngine

FIXTURE = Path(__file__).parents[1] / "fixtures/morning/synthetic.json"


def test_synthetic_end_to_end_has_citations_and_no_external_calls(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("network access from local morning loop")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    app, now = application(FIXTURE, tmp_path)
    run = app.tick(now=now)
    assert run.status is RunStatus.COMPLETED_WITH_GAPS
    artifact = json.loads(Path(run.result_ref).read_text())
    assert artifact["markdown"] == (FIXTURE.parent / "expected.md").read_text(
        encoding="utf-8"
    )
    items = [
        item for section in artifact["brief"]["sections"] for item in section["items"]
    ]
    attention = [item for item in items if item["section"] == "immediate_attention"]
    assert [item["title"] for item in attention] == [
        "Overdue: Review beam calculation",
        "Due today: Confirm design assumptions",
    ]
    upcoming = [
        item for item in items if item["section"] == "today_upcoming_commitments"
    ]
    assert any(item["title"] == "Atlas design review" for item in upcoming)
    assert all("Ended handover" not in item["title"] for item in upcoming)
    assert all("Completed survey" not in item["title"] for item in attention + upcoming)
    assert all("Inactive project" not in item["title"] for item in attention + upcoming)
    assert "Client: Synthetic Harbour Works" in attention[0]["text"]
    assert len(attention[0]["evidence_ids"]) == 3
    identities = {item["context_id"] for item in artifact["evidence"]}
    assert all(set(item["evidence_ids"]) <= identities for item in items)
    assert "local_corpus_may_be_stale" in artifact["markdown"]
    assert "connector_failure" in artifact["markdown"]
    assert not app.service.proposals_for_review(app.request)
    before = Path(run.result_ref).read_bytes()
    restarted, _ = application(FIXTURE, tmp_path)
    assert restarted.tick(now=now + timedelta(minutes=1)) is None
    assert Path(run.result_ref).read_bytes() == before
    assert len(list(tmp_path.glob("brief-*.json"))) == 1


def test_interrupted_worker_requires_explicit_recovery_then_safe_retry(tmp_path):
    app, now = application(FIXTURE, tmp_path)

    def crash():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        app.scheduler.tick(now=now, runner=crash)
    restarted, _ = application(FIXTURE, tmp_path)
    run = restarted.tick(now=now)
    assert run.status is RunStatus.RUNNING
    assert restarted.scheduler.status(now=now).recovery_required
    with pytest.raises(ValueError):
        restarted.retry(run.run_id, now=now)
    restarted.scheduler.recover_interrupted(run.run_id, now=now)
    retried = restarted.retry(run.run_id, now=now)
    assert retried.attempt == 2
    assert retried.status is RunStatus.COMPLETED_WITH_GAPS


def test_concurrent_tick_claims_exactly_one_execution(tmp_path, monkeypatch):
    app, now = application(FIXTURE, tmp_path)
    app.scheduler.initialise(now=now)
    barrier = Barrier(2)
    claim = app.scheduler.store.claim_run
    calls = []

    def racing_claim(run):
        barrier.wait(timeout=5)
        claim(run)

    def runner():
        calls.append("executed")
        return BriefRunResult("local-result")

    monkeypatch.setattr(app.scheduler.store, "claim_run", racing_claim)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: app.scheduler.tick(now=now, runner=runner), range(2))
        )
    assert calls == ["executed"]
    assert len({run.run_id for run in results}) == 1


def test_failure_is_sanitized_visible_and_retryable(tmp_path, monkeypatch):
    app, now = application(FIXTURE, tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("secret transport detail")

    monkeypatch.setattr(app.service, "daily_brief", broken)
    run = app.tick(now=now)
    assert run.status is RunStatus.FAILED
    assert "secret" not in str(run.to_dict())
    assert app.scheduler.status(now=now).recovery_required
    restarted, _ = application(FIXTURE, tmp_path)
    assert restarted.retry(run.run_id, now=now).status is RunStatus.COMPLETED_WITH_GAPS


@pytest.mark.parametrize(
    "status,age,expected",
    [
        (None, 0, "ingestion_status_unknown"),
        ("completed", 0, "recent_import_does_not_prove_mailbox_coverage"),
        ("completed", 3, "local_corpus_may_be_stale"),
        ("failed", 0, "ingestion_incomplete"),
        ("running", 0, "ingestion_incomplete"),
        ("completed", -1, "ingestion_timestamp_unknown"),
    ],
)
@pytest.mark.parametrize("has_recent", [True, False])
def test_email_import_coverage_is_not_inbox_coverage(
    tmp_path, status, age, expected, has_recent
):
    store = SQLiteEmailStore(tmp_path / "mail.db")
    store.initialise()
    if has_recent:
        store.add_many((_record("recent", NOW - timedelta(hours=1)),))
    if status:
        store.record_import_status("fixture", status, NOW - timedelta(days=age))
    adapter = EmailCorpusAdapter(
        EmailRetrievalAdapter(RetrievalEngine.from_store(store)), store, "archive"
    )
    response = IntelligenceService(_assembler((adapter,))).daily_brief(
        _request(), now=NOW
    )
    coverage = response.source_coverage[0]
    assert expected in coverage.reasons
    assert "local_archive_not_live_inbox" in coverage.reasons
    assert (
        "recent_evidence_exists" if has_recent else "no_evidence_in_period"
    ) in coverage.reasons
    assert coverage.selected_count == int(has_recent)


def _altered_app(tmp_path, change):
    data = json.loads(FIXTURE.read_text())
    change(data)
    fixture = tmp_path / "changed.json"
    fixture.write_text(json.dumps(data))
    return application(fixture, tmp_path / "state")


def test_conflicting_business_citation_rejected_not_overwritten(tmp_path):
    def conflict(data):
        actions = data["sources"][4]["records"]
        actions.append(dict(actions[0], title="Conflicting title"))

    app, now = _altered_app(tmp_path, conflict)
    response = app.service.daily_brief(app.request, now=now)
    assert all(item.context_id != "synthetic:actions:1" for item in response.evidence)
    assert any(
        "conflicting_evidence_id" in source.reasons
        for source in response.source_coverage
    )
    assert not any("Review beam" in item.title for item in response.daily_brief.items)


def test_stale_projects_cannot_create_action_urgency(tmp_path):
    app, now = _altered_app(
        tmp_path, lambda data: data["sources"][3].update(freshness="stale")
    )
    response = app.service.daily_brief(app.request, now=now)
    assert not any(
        item.section is BriefSectionKind.IMMEDIATE_ATTENTION
        for item in response.daily_brief.items
    )
    assert any(
        "project_current_state_unverified" in item.text
        for item in response.daily_brief.items
    )


def test_fair_source_instances_and_prefilter_counts_survive(tmp_path):
    app, now = application(FIXTURE, tmp_path)
    response = app.service.daily_brief(app.request, now=now)
    coverage = {
        source.source_instance_id: source for source in response.source_coverage
    }
    assert coverage["clients"].selected_count == 1
    assert coverage["projects"].selected_count == 2
    assert coverage["actions"].selected_count == 5
    assert coverage["actions"].pre_filter_count == 5
    assert len({item.context_id for item in response.evidence}) == len(
        response.evidence
    )


def test_retry_claim_is_compare_and_swap(tmp_path):
    app, now = application(FIXTURE, tmp_path)
    app.scheduler.initialise(now=now)
    run = app.scheduler.tick(
        now=now, runner=lambda: (_ for _ in ()).throw(ValueError())
    )
    replacement = replace(run, status=RunStatus.RUNNING, attempt=2)
    assert app.scheduler.store.transition_run(run, replacement)
    assert not app.scheduler.store.transition_run(run, replacement)


def test_existing_ui_runtime_discloses_archive_freshness_and_keeps_calendar_off(
    tmp_path,
):
    from edn.intelligence import IntelligenceRequest
    from edn.knowledge_graph.persistence import KnowledgeGraphStore
    from edn.ui.runtime import _intelligence_runtime

    store = SQLiteEmailStore(tmp_path / "mail.db")
    store.initialise()
    store.add_many((_record("recent", NOW),))
    service, principal, purpose, domain, classification, _, _ = _intelligence_runtime(
        store,
        KnowledgeGraphStore(tmp_path / "graph.db"),
        False,
        tmp_path / "operations.db",
    )
    response = service.daily_brief(
        IntelligenceRequest("morning", principal, purpose, domain, classification),
        now=NOW,
    )
    coverage = {source.capability_id: source for source in response.source_coverage}
    assert "ingestion_status_unknown" in coverage["email.retrieve"].reasons
    assert coverage["calendar.search"].status == "unavailable"
    assert not any(
        item.section is BriefSectionKind.IMMEDIATE_ATTENTION
        for item in response.daily_brief.items
    )
