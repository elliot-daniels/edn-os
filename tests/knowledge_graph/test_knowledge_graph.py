"""Synthetic tests for extraction, persistence, and retrieval integration."""

from datetime import UTC, datetime
from pathlib import Path

from edn.knowledge_graph.entities import EntityType
from edn.knowledge_graph.extractor import KnowledgeExtractor
from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.knowledge_graph.pipeline import KnowledgeExtractionPipeline
from edn.knowledge_graph.retrieval import KnowledgeCandidateRetriever
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import RetrievalEngine


def _record(
    key: str,
    *,
    subject: str = "CRQ123456 network change",
    body: str = "Engineer commissioned an MX304 at Testville using Juniper tooling.",
    sender: str = "Alex Engineer <alex@example.test>",
) -> EmailRecord:
    return EmailRecord(
        source_record_key=key,
        folder_path="Inbox/Synthetic",
        subject=subject,
        sender=sender,
        recipients_to=("operator@example.test",),
        recipients_cc=(),
        recipients_bcc=(),
        sent_at=datetime(2026, 1, 1, tzinfo=UTC),
        received_at=None,
        message_id=f"<{key}@example.test>",
        body_text=body,
    )


def _stores(tmp_path: Path) -> tuple[SQLiteEmailStore, KnowledgeGraphStore]:
    database = tmp_path / "memory.db"
    emails = SQLiteEmailStore(database)
    emails.initialise()
    return emails, KnowledgeGraphStore(database)


def test_extracts_named_entities_identifiers_and_person() -> None:
    result = KnowledgeExtractor().extract(
        _record(
            "one",
            body=(
                "Alex commissioned MX304 with Juniper at Pimba for Services Australia."
            ),
        )
    )
    names = {(item.entity_type, item.canonical_name) for item in result.mentions}
    assert (EntityType.EQUIPMENT, "MX304") in names
    assert (EntityType.TECHNOLOGY, "Juniper") in names
    assert (EntityType.SITE, "Pimba") in names
    assert (EntityType.CLIENT, "Services Australia") in names
    assert (EntityType.PROJECT, "CRQ123456") in names
    assert (EntityType.PERSON, "Alex Engineer") in names


def test_relationships_preserve_expected_direction() -> None:
    result = KnowledgeExtractor().extract(
        _record("one", body="MX304 commissioning at Pimba for CRQ123456.")
    )
    predicates = {item.predicate for item in result.relationships}
    assert "works_on" in predicates
    assert "uses" in predicates
    assert "commissioned_at" in predicates


def test_duplicate_mentions_merge_but_preserve_field_occurrences(
    tmp_path: Path,
) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(_record("one", subject="MX304", body="MX304 MX304"))
    KnowledgeExtractionPipeline(emails, graph).run()
    entities = graph.lookup_entities("MX304")
    assert len(entities) == 1
    assert entities[0].source_count == 1
    assert entities[0].occurrence_count == 2


def test_entity_and_relationship_sources_resolve_to_email(tmp_path: Path) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(_record("evidence", body="CRQ123456 uses Juniper."))
    KnowledgeExtractionPipeline(emails, graph).run()
    project = graph.lookup_entities("CRQ123456")[0]
    details = graph.entity_details(project.entity_id)
    assert details is not None
    assert details.source_record_keys == ("evidence",)
    assert emails.get(details.source_record_keys[0]) is not None
    assert any(item.predicate == "uses" for item in details.related_entities)


def test_incremental_update_processes_only_new_emails(tmp_path: Path) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(_record("one"))
    pipeline = KnowledgeExtractionPipeline(emails, graph)
    assert pipeline.run().processed_emails == 1
    assert pipeline.run().processed_emails == 0
    emails.add(_record("two", subject="Provisioning Requests"))
    assert pipeline.run().processed_emails == 1
    assert graph.lookup_entities("Provisioning Requests")


def test_interrupted_batch_resumes_after_last_committed_email(tmp_path: Path) -> None:
    emails, graph = _stores(tmp_path)
    emails.add_many((_record("one"), _record("two"), _record("three")))
    pipeline = KnowledgeExtractionPipeline(emails, graph)
    assert pipeline.run(max_records=2).processed_emails == 2
    assert pipeline.run().processed_emails == 1


def test_entity_lookup_is_normalized_and_bounded(tmp_path: Path) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(_record("one", body="Services Australia and Juniper."))
    KnowledgeExtractionPipeline(emails, graph).run()
    assert graph.lookup_entities("services australia", limit=1)[0].canonical_name == (
        "Services Australia"
    )


def test_ask_retrieval_merges_entity_supported_email(tmp_path: Path) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(
        _record(
            "supported",
            subject="Engineering update",
            body="The MX304 installation completed successfully.",
        )
    )
    KnowledgeExtractionPipeline(emails, graph).run()
    engine = RetrievalEngine.from_store(
        emails,
        supplemental_retrievers=(KnowledgeCandidateRetriever(graph, emails),),
    )
    evidence = engine.retrieve("What happened with MX304?", limit=5)
    assert evidence[0].source_record_key == "supported"
    assert "knowledge entity support" in evidence[0].explanations


def test_exact_entity_lookup_precedes_partial_matches(tmp_path: Path) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(_record("exact", body="Services Australia."))
    emails.add(_record("partial", body="NBN service in Adelaide, Australia."))
    KnowledgeExtractionPipeline(emails, graph).run()
    matches = graph.lookup_entities("Services Australia")
    assert matches[0].canonical_name == "Services Australia"


def test_knowledge_retrieval_ignores_conversational_query_noise(
    tmp_path: Path,
) -> None:
    emails, graph = _stores(tmp_path)
    emails.add(_record("person", sender="What Person <what@example.test>"))
    KnowledgeExtractionPipeline(emails, graph).run()
    engine = RetrievalEngine.from_store(
        emails,
        supplemental_retrievers=(KnowledgeCandidateRetriever(graph, emails),),
    )
    evidence = engine.retrieve("What happened with UNKNOWN900?", limit=5)
    assert all("knowledge entity support" not in item.explanations for item in evidence)
