"""SQLite persistence for normalized knowledge entities and evidence links."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from edn.knowledge_graph.entities import (
    EntityDetails,
    EntityMention,
    EntityType,
    ExtractionResult,
    KnowledgeEntity,
    RelatedEntity,
)
from edn.knowledge_graph.rules import normalize_entity_name

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS knowledge_entities (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(entity_type, normalized_name)
);
CREATE TABLE IF NOT EXISTS knowledge_entity_occurrences (
    entity_id INTEGER NOT NULL REFERENCES knowledge_entities(id) ON DELETE CASCADE,
    source_record_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    matched_text TEXT NOT NULL,
    PRIMARY KEY(entity_id, source_record_key, field_name)
);
CREATE INDEX IF NOT EXISTS knowledge_occurrences_source
ON knowledge_entity_occurrences(source_record_key);
CREATE TABLE IF NOT EXISTS knowledge_relationships (
    id INTEGER PRIMARY KEY,
    subject_entity_id INTEGER NOT NULL REFERENCES knowledge_entities(id),
    predicate TEXT NOT NULL,
    object_entity_id INTEGER NOT NULL REFERENCES knowledge_entities(id),
    UNIQUE(subject_entity_id, predicate, object_entity_id)
);
CREATE TABLE IF NOT EXISTS knowledge_relationship_sources (
    relationship_id INTEGER NOT NULL
        REFERENCES knowledge_relationships(id) ON DELETE CASCADE,
    source_record_key TEXT NOT NULL,
    PRIMARY KEY(relationship_id, source_record_key)
);
CREATE TABLE IF NOT EXISTS knowledge_extraction_state (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    last_email_id INTEGER NOT NULL,
    rule_version TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class RuleVersionMismatchError(RuntimeError):
    """Raised when incremental data was produced by another rule version."""


class KnowledgeGraphStore:
    """Persist and query the structured layer without modifying email rows."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        read_only: bool = False,
        timeout_seconds: float = 30.0,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        self._database_path = Path(database_path)
        self._read_only = read_only
        self._timeout_seconds = timeout_seconds
        self._busy_timeout_ms = busy_timeout_ms

    def _open(self) -> sqlite3.Connection:
        if self._read_only:
            uri = self._database_path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=self._timeout_seconds)
        else:
            connection = sqlite3.connect(
                self._database_path, timeout=self._timeout_seconds
            )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()
        try:
            yield connection
            if not self._read_only:
                connection.commit()
        finally:
            connection.close()

    def initialise(self, rule_version: str) -> None:
        """Create graph tables and validate the incremental rule version."""
        if self._read_only:
            raise sqlite3.OperationalError("store is read-only")
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            row = connection.execute(
                """
                SELECT rule_version FROM knowledge_extraction_state
                WHERE singleton_id = 1
                """
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO knowledge_extraction_state
                    (singleton_id, last_email_id, rule_version, updated_at)
                    VALUES (1, 0, ?, ?)
                    """,
                    (rule_version, datetime.now(UTC).isoformat()),
                )
            elif str(row["rule_version"]) != rule_version:
                raise RuleVersionMismatchError(
                    "Knowledge rules changed; rebuild is required before continuing."
                )

    def schema_available(self) -> bool:
        """Return whether the graph schema exists without attempting writes."""
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type = 'table' AND name = 'knowledge_entities'
                    """
                ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    def last_email_id(self) -> int:
        """Return the last atomically processed email row id."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT last_email_id FROM knowledge_extraction_state
                WHERE singleton_id = 1
                """
            ).fetchone()
        return 0 if row is None else int(row["last_email_id"])

    def apply(self, email_id: int, result: ExtractionResult) -> None:
        """Persist one email's graph changes and checkpoint atomically."""
        self.apply_batch(((email_id, result),))

    def apply_batch(
        self,
        items: Sequence[tuple[int, ExtractionResult]],
    ) -> None:
        """Persist one bounded page and its final checkpoint atomically."""
        if self._read_only:
            raise sqlite3.OperationalError("store is read-only")
        if not items:
            return
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for _, result in items:
                self._apply_result(connection, result)
            connection.execute(
                """
                UPDATE knowledge_extraction_state
                SET last_email_id = ?, updated_at = ? WHERE singleton_id = 1
                """,
                (items[-1][0], datetime.now(UTC).isoformat()),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _apply_result(
        self,
        connection: sqlite3.Connection,
        result: ExtractionResult,
    ) -> None:
        entity_ids: dict[tuple[EntityType, str], int] = {}
        for mention in result.mentions:
            entity_ids[(mention.entity_type, mention.normalized_name)] = (
                self._upsert_mention(connection, mention, result.source_record_key)
            )
        for fact in result.relationships:
            subject_id = entity_ids[(fact.subject_type, fact.subject_name)]
            object_id = entity_ids[(fact.object_type, fact.object_name)]
            connection.execute(
                """
                    INSERT OR IGNORE INTO knowledge_relationships
                    (subject_entity_id, predicate, object_entity_id)
                    VALUES (?, ?, ?)
                    """,
                (subject_id, fact.predicate, object_id),
            )
            relationship = connection.execute(
                """
                    SELECT id FROM knowledge_relationships
                    WHERE subject_entity_id = ? AND predicate = ?
                      AND object_entity_id = ?
                    """,
                (subject_id, fact.predicate, object_id),
            ).fetchone()
            if relationship is None:
                raise RuntimeError("relationship upsert did not return an id")
            connection.execute(
                """
                    INSERT OR IGNORE INTO knowledge_relationship_sources
                    (relationship_id, source_record_key) VALUES (?, ?)
                    """,
                (int(relationship["id"]), result.source_record_key),
            )

    @staticmethod
    def _upsert_mention(
        connection: sqlite3.Connection,
        mention: EntityMention,
        source_record_key: str,
    ) -> int:
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_entities
            (entity_type, canonical_name, normalized_name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                mention.entity_type.value,
                mention.canonical_name,
                mention.normalized_name,
                datetime.now(UTC).isoformat(),
            ),
        )
        row = connection.execute(
            """
            SELECT id FROM knowledge_entities
            WHERE entity_type = ? AND normalized_name = ?
            """,
            (mention.entity_type.value, mention.normalized_name),
        ).fetchone()
        if row is None:
            raise RuntimeError("entity upsert did not return an id")
        entity_id = int(row["id"])
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_entity_occurrences
            (entity_id, source_record_key, field_name, matched_text)
            VALUES (?, ?, ?, ?)
            """,
            (entity_id, source_record_key, mention.field_name, mention.matched_text),
        )
        return entity_id

    def list_entities(
        self,
        entity_type: EntityType | None = None,
        *,
        limit: int = 100,
    ) -> tuple[KnowledgeEntity, ...]:
        """List entities by source support, bounded for UI and APIs."""
        if limit < 1:
            raise ValueError("limit must be at least 1")
        parameters: list[object] = []
        where = ""
        if entity_type is not None:
            where = "WHERE e.entity_type = ?"
            parameters.append(entity_type.value)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT e.*, COUNT(o.entity_id) AS occurrence_count,
                       COUNT(DISTINCT o.source_record_key) AS source_count
                FROM knowledge_entities e
                JOIN knowledge_entity_occurrences o ON o.entity_id = e.id
                {where}
                GROUP BY e.id
                ORDER BY source_count DESC, e.canonical_name COLLATE NOCASE, e.id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return tuple(self._row_to_entity(row) for row in rows)

    def lookup_entities(
        self, query: str, *, limit: int = 10
    ) -> tuple[KnowledgeEntity, ...]:
        """Find normalized entity names using bounded indexed graph data."""
        terms = tuple(dict.fromkeys(re.findall(r"[A-Za-z0-9._/-]+", query.casefold())))
        if not terms:
            return ()
        clauses = " OR ".join("e.normalized_name LIKE ?" for _ in terms)
        normalized_query = normalize_entity_name(query)
        parameters: list[object] = [f"%{term}%" for term in terms]
        parameters.append(normalized_query)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT e.*, COUNT(o.entity_id) AS occurrence_count,
                       COUNT(DISTINCT o.source_record_key) AS source_count
                FROM knowledge_entities e
                JOIN knowledge_entity_occurrences o ON o.entity_id = e.id
                WHERE {clauses}
                GROUP BY e.id
                ORDER BY
                  CASE WHEN e.normalized_name = ? THEN 0 ELSE 1 END,
                  source_count DESC, e.canonical_name COLLATE NOCASE
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return tuple(self._row_to_entity(row) for row in rows)

    def source_keys_for_query(self, query: str, *, limit: int) -> tuple[str, ...]:
        """Return evidence keys for matching entities without reading email bodies."""
        entities = self.lookup_entities(query, limit=10)
        if not entities:
            return ()
        normalized_query = normalize_entity_name(query)
        exact = tuple(
            entity for entity in entities if entity.normalized_name == normalized_query
        )
        entities = exact or entities
        placeholders = ",".join("?" for _ in entities)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT o.source_record_key, COUNT(DISTINCT o.entity_id) AS matches
                FROM knowledge_entity_occurrences o
                WHERE o.entity_id IN ({placeholders})
                GROUP BY o.source_record_key
                ORDER BY matches DESC, o.source_record_key
                LIMIT ?
                """,
                [*(entity.entity_id for entity in entities), limit],
            ).fetchall()
        return tuple(str(row["source_record_key"]) for row in rows)

    def entity_details(self, entity_id: int) -> EntityDetails | None:
        """Load one entity with bounded neighbours and all supporting keys."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT e.*, COUNT(o.entity_id) AS occurrence_count,
                       COUNT(DISTINCT o.source_record_key) AS source_count
                FROM knowledge_entities e
                JOIN knowledge_entity_occurrences o ON o.entity_id = e.id
                WHERE e.id = ? GROUP BY e.id
                """,
                (entity_id,),
            ).fetchone()
            if row is None:
                return None
            entity = self._row_to_entity(row)
            relation_rows = connection.execute(
                """
                SELECT r.predicate, r.subject_entity_id, r.object_entity_id,
                       e.*, COUNT(DISTINCT s.source_record_key) AS source_count,
                       COUNT(o.entity_id) AS occurrence_count
                FROM knowledge_relationships r
                JOIN knowledge_entities e
                  ON e.id = CASE WHEN r.subject_entity_id = ?
                                 THEN r.object_entity_id ELSE r.subject_entity_id END
                JOIN knowledge_relationship_sources s ON s.relationship_id = r.id
                JOIN knowledge_entity_occurrences o ON o.entity_id = e.id
                WHERE r.subject_entity_id = ? OR r.object_entity_id = ?
                GROUP BY r.id, e.id
                ORDER BY source_count DESC, e.canonical_name COLLATE NOCASE
                LIMIT 50
                """,
                (entity_id, entity_id, entity_id),
            ).fetchall()
            source_rows = connection.execute(
                """
                SELECT DISTINCT source_record_key
                FROM knowledge_entity_occurrences
                WHERE entity_id = ? ORDER BY source_record_key LIMIT 100
                """,
                (entity_id,),
            ).fetchall()
        related = tuple(
            RelatedEntity(
                predicate=str(item["predicate"]),
                entity=self._row_to_entity(item),
                direction=(
                    "outgoing"
                    if int(item["subject_entity_id"]) == entity_id
                    else "incoming"
                ),
                source_count=int(item["source_count"]),
            )
            for item in relation_rows
        )
        return EntityDetails(
            entity=entity,
            related_entities=related,
            source_record_keys=tuple(
                str(item["source_record_key"]) for item in source_rows
            ),
        )

    def counts(self) -> tuple[int, int, int]:
        """Return processed email, entity, and relationship totals."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                  (
                    SELECT last_email_id FROM knowledge_extraction_state
                    WHERE singleton_id=1
                  ) processed,
                  (SELECT COUNT(*) FROM knowledge_entities) entities,
                  (SELECT COUNT(*) FROM knowledge_relationships) relationships
                """
            ).fetchone()
        if row is None:
            return (0, 0, 0)
        return (
            int(row["processed"] or 0),
            int(row["entities"]),
            int(row["relationships"]),
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> KnowledgeEntity:
        return KnowledgeEntity(
            entity_id=int(row["id"]),
            entity_type=EntityType(str(row["entity_type"])),
            canonical_name=str(row["canonical_name"]),
            normalized_name=str(row["normalized_name"]),
            occurrence_count=int(row["occurrence_count"]),
            source_count=int(row["source_count"]),
        )
