"""Incremental, resumable knowledge extraction pipeline and local CLI."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from edn.knowledge_graph.extractor import KnowledgeExtractor
from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.knowledge_graph.rules import RULE_VERSION
from edn.memory.storage import SQLiteEmailStore


@dataclass(frozen=True, slots=True)
class ExtractionReport:
    """Aggregate results for one incremental extraction run."""

    processed_emails: int
    extracted_mentions: int
    extracted_relationships: int
    last_email_id: int
    elapsed_seconds: float


class KnowledgeExtractionPipeline:
    """Process bounded email pages and atomically advance graph checkpoints."""

    def __init__(
        self,
        email_store: SQLiteEmailStore,
        graph_store: KnowledgeGraphStore,
        *,
        extractor: KnowledgeExtractor | None = None,
        batch_size: int = 250,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        self._email_store = email_store
        self._graph_store = graph_store
        self._extractor = extractor or KnowledgeExtractor()
        self._batch_size = batch_size

    def run(
        self,
        *,
        max_records: int | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> ExtractionReport:
        """Resume after the last committed email and stop cleanly on interruption."""
        if max_records is not None and max_records < 0:
            raise ValueError("max_records must not be negative")
        started = time.perf_counter()
        self._graph_store.initialise(RULE_VERSION)
        last_email_id = self._graph_store.last_email_id()
        processed = mentions = relationships = 0
        while max_records is None or processed < max_records:
            remaining = self._batch_size
            if max_records is not None:
                remaining = min(remaining, max_records - processed)
            if remaining == 0:
                break
            page = self._email_store.records_after_id(last_email_id, limit=remaining)
            if not page:
                break
            extracted = tuple(
                (stored.email_id, self._extractor.extract(stored.record))
                for stored in page
            )
            self._graph_store.apply_batch(extracted)
            for stored, (_, result) in zip(page, extracted, strict=True):
                last_email_id = stored.email_id
                processed += 1
                mentions += len(result.mentions)
                relationships += len(result.relationships)
            if progress is not None:
                progress(processed, last_email_id)
        return ExtractionReport(
            processed_emails=processed,
            extracted_mentions=mentions,
            extracted_relationships=relationships,
            last_email_id=last_email_id,
            elapsed_seconds=time.perf_counter() - started,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run deterministic extraction against an explicitly selected database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args(argv)
    email_store = SQLiteEmailStore(args.database, read_only=True)
    graph_store = KnowledgeGraphStore(args.database)
    pipeline = KnowledgeExtractionPipeline(
        email_store, graph_store, batch_size=args.batch_size
    )
    report = pipeline.run(
        progress=lambda count, email_id: (
            print(f"Processed {count:,} emails (checkpoint {email_id:,})")
            if count % 500 == 0
            else None
        )
    )
    processed, entities, relationships = graph_store.counts()
    print(
        f"Complete: {report.processed_emails:,} new emails, "
        f"{entities:,} entities, {relationships:,} relationships, "
        f"checkpoint {processed:,}, {report.elapsed_seconds:.2f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
