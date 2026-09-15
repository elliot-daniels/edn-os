"""Daily briefs retrieve a bounded local time window, not generic FTS words."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from tests.intelligence.test_context_alpha import NOW, _assembler, _request

from edn.intelligence import EmailRetrievalAdapter, IntelligenceService
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import RetrievalEngine
from edn.retrieval.keyword import SQLiteFTSKeywordRetriever


def _record(key, sent_at):
    return EmailRecord(
        key,
        "Inbox",
        "Atlas design review",
        "engineer@example.test",
        (),
        (),
        (),
        sent_at,
        None,
        None,
        "Drawing revision is available.",
    )


def _store(tmp_path):
    store = SQLiteEmailStore(tmp_path / "memory.db")
    store.initialise()
    store.add_many(
        (
            _record("recent", NOW - timedelta(hours=1)),
            _record("old", NOW - timedelta(days=8)),
            _record("future", NOW + timedelta(seconds=1)),
            _record("undated", None),
            _record("naive", NOW.replace(tzinfo=None)),
        )
    )
    return store


def test_daily_brief_finds_recent_mail_without_matching_generic_prompt(tmp_path):
    store = _store(tmp_path)
    engine = RetrievalEngine.from_store(store)
    adapter = EmailRetrievalAdapter(engine)
    service = IntelligenceService(_assembler((adapter,)))
    assert engine.retrieve("What do I need to know today?") == ()
    response = service.daily_brief(_request(), now=NOW)
    assert len(response.evidence) == 1
    item = response.evidence[0]
    assert item.provenance[0].record.source_record_key == "recent"
    assert item.timestamp_kind == "email_sent_at"
    assert item.source_timestamp == NOW - timedelta(hours=1)
    assert response.source_coverage[0].selected_count == 1
    assert store.count() == 5


def test_ordinary_question_search_preserves_keyword_semantics(tmp_path):
    store = _store(tmp_path)
    service = IntelligenceService(
        _assembler((EmailRetrievalAdapter(RetrievalEngine.from_store(store)),))
    )
    response = service.answer(replace(_request(), query="Atlas"), now=NOW)
    keys = {x.provenance[0].record.source_record_key for x in response.evidence}
    assert "old" in keys  # ordinary search is not silently limited to seven days
    naive = next(
        x
        for x in response.evidence
        if x.provenance[0].record.source_record_key == "naive"
    )
    assert naive.source_timestamp is None
    assert naive.timestamp_kind is None


def test_recent_window_compares_instants_and_tie_breaks_by_source_key(tmp_path):
    store = SQLiteEmailStore(tmp_path / "offsets.db")
    store.initialise()
    since = NOW - timedelta(days=7)
    east = timezone(timedelta(hours=10))
    store.add_many(
        (
            _record("b", NOW.astimezone(east)),
            _record("a", NOW),
            _record("boundary", since),
            _record("too-old", since - timedelta(seconds=1)),
        )
    )
    assert [r.source_record_key for r in store.recent(since=since, until=NOW)] == [
        "a",
        "b",
        "boundary",
    ]
    assert [
        r.source_record_key for r in store.recent(since=since, until=NOW, limit=1)
    ] == ["a"]


@pytest.mark.parametrize(
    "since,until,limit",
    [
        (NOW, NOW - timedelta(days=1), 5),
        (NOW.replace(tzinfo=None), NOW, 5),
        (NOW, NOW, 0),
        (NOW, NOW, 26),
    ],
)
def test_recent_query_rejects_invalid_bounds(tmp_path, since, until, limit):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.recent(since=since, until=until, limit=limit)


def test_recent_read_works_without_writing_existing_database(tmp_path):
    _store(tmp_path)
    path = tmp_path / "memory.db"
    before = path.read_bytes()
    read_only = SQLiteEmailStore(path, read_only=True)
    result = read_only.recent(since=NOW - timedelta(days=7), until=NOW)
    assert len(result) == 1
    assert path.read_bytes() == before


def test_unconfigured_recent_backend_becomes_explicit_gap(tmp_path):
    engine = RetrievalEngine(SQLiteFTSKeywordRetriever(_store(tmp_path)))
    response = IntelligenceService(
        _assembler((EmailRetrievalAdapter(engine),))
    ).daily_brief(_request(), now=NOW)
    assert response.evidence == ()
    assert response.source_coverage[0].status == "unavailable"


def test_future_mail_does_not_enter_recent_evidence_across_offset_boundary(tmp_path):
    store = SQLiteEmailStore(tmp_path / "future.db")
    store.initialise()
    store.add(
        _record(
            "future-offset",
            (NOW + timedelta(hours=1)).astimezone(timezone(timedelta(hours=-10))),
        )
    )
    assert store.recent(since=datetime(2026, 1, 1, tzinfo=UTC), until=NOW) == ()
