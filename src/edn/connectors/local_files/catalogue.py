"""Metadata-only SQLite catalogue for Local Files discovery and ingestion."""

# ruff: noqa: E501 -- SQL statements remain readable as complete clauses.

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import cast

from edn.connectors.local_files.models import (
    CandidateState,
    CoverageOpportunity,
    CoverageStatus,
    DiscoverySummary,
    FileCandidate,
    UnsupportedCapabilitySignal,
)
from edn.core import Classification, SecurityDomain, UniversalRecordRef

SCHEMA_VERSION = 2
_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_metadata(
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery_runs(
    run_id TEXT PRIMARY KEY,
    root_count INTEGER NOT NULL DEFAULT 0,
    complete INTEGER NOT NULL DEFAULT 0,
    excluded_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS traversal_cursors(
    cursor_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    connector_version TEXT NOT NULL,
    state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates(
    resource_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    root_id TEXT NOT NULL,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    category TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER NOT NULL,
    modified_at TEXT NOT NULL,
    created_at TEXT,
    hidden INTEGER NOT NULL,
    symlink INTEGER NOT NULL,
    security_domain_json TEXT NOT NULL,
    classification_json TEXT NOT NULL,
    metadata_fingerprint TEXT NOT NULL,
    supported_ingestion INTEGER NOT NULL,
    missing_capability TEXT,
    state TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0,
    record_json TEXT,
    content_hash TEXT
);
CREATE INDEX IF NOT EXISTS candidates_run ON candidates(run_id, resource_id);
CREATE INDEX IF NOT EXISTS candidates_category ON candidates(run_id, category);
"""


class CandidateCatalogue:
    def __init__(
        self,
        database_path: str | Path,
        *,
        connection_timeout_seconds: float = 30.0,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        self._path = Path(database_path)
        self._connection_timeout = connection_timeout_seconds
        self._busy_timeout_ms = busy_timeout_ms

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path, timeout=self._connection_timeout)
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialise(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            row = connection.execute(
                "SELECT version FROM schema_metadata WHERE component = 'local_files'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_metadata(component, version) VALUES ('local_files', ?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) == 1:
                columns = {
                    str(item[1])
                    for item in connection.execute("PRAGMA table_info(discovery_runs)")
                }
                if "excluded_count" not in columns:
                    connection.execute(
                        "ALTER TABLE discovery_runs ADD COLUMN excluded_count INTEGER NOT NULL DEFAULT 0"
                    )
                connection.execute(
                    "UPDATE schema_metadata SET version = ? WHERE component = 'local_files'",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported Local Files catalogue schema")

    def begin_run(self, run_id: str, root_count: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO discovery_runs(run_id, root_count, complete)
                VALUES (?, ?, 0)
                ON CONFLICT(run_id) DO NOTHING""",
                (run_id, root_count),
            )

    def complete_run(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE discovery_runs SET complete = 1 WHERE run_id = ?", (run_id,)
            )

    def add_excluded(self, run_id: str, count: int) -> None:
        if count < 0:
            raise ValueError("excluded count must not be negative")
        with self._connect() as connection:
            connection.execute(
                "UPDATE discovery_runs SET excluded_count = excluded_count + ? WHERE run_id = ?",
                (count, run_id),
            )

    def save_traversal_cursor(
        self,
        cursor_id: str,
        run_id: str,
        configuration_hash: str,
        connector_version: str,
        state_json: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO traversal_cursors(cursor_id, run_id, configuration_hash, connector_version, state_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cursor_id) DO UPDATE SET state_json=excluded.state_json""",
                (cursor_id, run_id, configuration_hash, connector_version, state_json),
            )

    def traversal_cursor(
        self,
        cursor_id: str,
        run_id: str,
        configuration_hash: str,
        connector_version: str,
    ) -> str:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT state_json FROM traversal_cursors
                WHERE cursor_id=? AND run_id=? AND configuration_hash=? AND connector_version=?""",
                (cursor_id, run_id, configuration_hash, connector_version),
            ).fetchone()
        if row is None:
            raise ValueError("durable traversal cursor is missing or incompatible")
        return str(row["state_json"])

    def run_complete(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT complete FROM discovery_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return row is not None and bool(row["complete"])

    def upsert_many(self, candidates: Sequence[FileCandidate]) -> None:
        if not candidates:
            return
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                """INSERT INTO candidates(
                    resource_id, run_id, root_id, path, filename, extension,
                    category, mime_type, size_bytes, modified_at, created_at,
                    hidden, symlink, security_domain_json, classification_json,
                    metadata_fingerprint, supported_ingestion, missing_capability,
                    state, warnings_json, selected, record_json, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    run_id=excluded.run_id, root_id=excluded.root_id,
                    path=excluded.path, filename=excluded.filename,
                    extension=excluded.extension, category=excluded.category,
                    mime_type=excluded.mime_type, size_bytes=excluded.size_bytes,
                    modified_at=excluded.modified_at, created_at=excluded.created_at,
                    hidden=excluded.hidden, symlink=excluded.symlink,
                    security_domain_json=excluded.security_domain_json,
                    classification_json=excluded.classification_json,
                    metadata_fingerprint=excluded.metadata_fingerprint,
                    supported_ingestion=excluded.supported_ingestion,
                    missing_capability=excluded.missing_capability,
                    state=CASE WHEN candidates.state='ingested' THEN candidates.state ELSE excluded.state END,
                    warnings_json=excluded.warnings_json""",
                tuple(_candidate_values(candidate) for candidate in candidates),
            )

    def get(self, resource_id: str) -> FileCandidate | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM candidates WHERE resource_id = ?", (resource_id,)
            ).fetchone()
        return None if row is None else _row_to_candidate(row)

    def selected(self, resource_ids: Sequence[str]) -> tuple[FileCandidate, ...]:
        if not resource_ids:
            return ()
        identifiers = tuple(dict.fromkeys(resource_ids))
        placeholders = ",".join("?" for _ in identifiers)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM candidates WHERE resource_id IN ({placeholders}) ORDER BY resource_id",
                identifiers,
            ).fetchall()
        candidates = tuple(_row_to_candidate(row) for row in rows)
        if len(candidates) != len(identifiers):
            raise ValueError("selection contains an unknown candidate")
        return candidates

    def candidates_for_run(self, run_id: str) -> tuple[FileCandidate, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM candidates WHERE run_id = ? ORDER BY resource_id",
                (run_id,),
            ).fetchall()
        return tuple(_row_to_candidate(row) for row in rows)

    def mark_selected(self, resource_ids: Sequence[str]) -> None:
        if not resource_ids:
            raise ValueError("candidate selection must not be empty")
        identifiers = tuple(dict.fromkeys(resource_ids))
        placeholders = ",".join("?" for _ in identifiers)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE candidates SET selected = 0")
            cursor = connection.execute(
                f"UPDATE candidates SET selected = 1 WHERE resource_id IN ({placeholders})",
                identifiers,
            )
            if cursor.rowcount != len(identifiers):
                raise ValueError("selection contains an unknown candidate")

    def mark_ingested(
        self, resource_id: str, record: UniversalRecordRef, content_hash: str
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE candidates SET state = ?, record_json = ?, content_hash = ?
                WHERE resource_id = ?""",
                (
                    CandidateState.INGESTED.value,
                    _json(record.to_dict()),
                    content_hash,
                    resource_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(resource_id)

    def mark_source_changed(self, resource_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE candidates SET state = ? WHERE resource_id = ?",
                (CandidateState.SOURCE_CHANGED.value, resource_id),
            )

    def records(self, resource_ids: Sequence[str]) -> tuple[UniversalRecordRef, ...]:
        return tuple(
            candidate.record
            for candidate in self.selected(resource_ids)
            if candidate.record is not None
        )

    def summary(self, run_id: str) -> DiscoverySummary:
        with self._connect() as connection:
            run = connection.execute(
                "SELECT root_count, excluded_count FROM discovery_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            totals = connection.execute(
                """SELECT COUNT(*) total, COALESCE(SUM(size_bytes), 0) bytes,
                    SUM(CASE WHEN state='ingested' THEN 1 ELSE 0 END) known,
                    SUM(CASE WHEN supported_ingestion=1 THEN 1 ELSE 0 END) supported,
                    SUM(CASE WHEN supported_ingestion=0 THEN 1 ELSE 0 END) unsupported,
                    SUM(CASE WHEN warnings_json != '[]' THEN 1 ELSE 0 END) warnings
                FROM candidates WHERE run_id = ?""",
                (run_id,),
            ).fetchone()
            categories = connection.execute(
                """SELECT category, COUNT(*) total FROM candidates
                WHERE run_id = ? GROUP BY category ORDER BY category""",
                (run_id,),
            ).fetchall()
            extensions = connection.execute(
                """SELECT extension, COUNT(*) total FROM candidates
                WHERE run_id = ? GROUP BY extension ORDER BY extension""",
                (run_id,),
            ).fetchall()
            ages = connection.execute(
                """SELECT CASE
                    WHEN modified_at >= datetime('now', '-30 day') THEN '0-30-days'
                    WHEN modified_at >= datetime('now', '-365 day') THEN '31-365-days'
                    ELSE 'over-365-days' END age, COUNT(*) total
                FROM candidates WHERE run_id = ? GROUP BY age ORDER BY age""",
                (run_id,),
            ).fetchall()
            unsupported = connection.execute(
                """SELECT category, COUNT(*) total, SUM(size_bytes) bytes,
                    missing_capability FROM candidates
                WHERE run_id = ? AND supported_ingestion = 0
                GROUP BY category, missing_capability ORDER BY category""",
                (run_id,),
            ).fetchall()
            coverage_rows = connection.execute(
                """SELECT category, supported_ingestion, missing_capability,
                    extension, size_bytes, security_domain_json,
                    classification_json, CASE
                    WHEN modified_at >= datetime('now', '-30 day') THEN '0-30-days'
                    WHEN modified_at >= datetime('now', '-365 day') THEN '31-365-days'
                    ELSE 'over-365-days' END age
                FROM candidates WHERE run_id = ?""",
                (run_id,),
            ).fetchall()
        assert totals is not None
        total_records = int(totals["total"])
        total_bytes = int(totals["bytes"] or 0)
        return DiscoverySummary(
            run_id,
            int(run["root_count"]),
            int(totals["total"]),
            int(totals["known"] or 0),
            int(totals["supported"] or 0),
            int(totals["unsupported"] or 0),
            int(run["excluded_count"] or 0),
            int(totals["warnings"] or 0),
            int(totals["bytes"] or 0),
            tuple((str(row["category"]), int(row["total"])) for row in categories),
            tuple(
                (str(row["extension"] or "[none]"), int(row["total"]))
                for row in extensions
            ),
            tuple((str(row["age"]), int(row["total"])) for row in ages),
            tuple(
                UnsupportedCapabilitySignal(
                    str(row["category"]),
                    int(row["total"]),
                    int(row["bytes"] or 0),
                    str(row["missing_capability"]),
                )
                for row in unsupported
            ),
            _coverage_opportunities(coverage_rows, total_records, total_bytes),
        )


def _coverage_opportunities(
    rows: Sequence[sqlite3.Row], total_records: int, total_bytes: int
) -> tuple[CoverageOpportunity, ...]:
    grouped: dict[
        tuple[str, CoverageStatus, str | None],
        dict[str, object],
    ] = {}
    for row in rows:
        supported = bool(row["supported_ingestion"])
        missing = (
            None
            if row["missing_capability"] is None
            else str(row["missing_capability"])
        )
        status = _coverage_status(supported, missing)
        key = (str(row["category"]), status, missing)
        group = grouped.setdefault(
            key,
            {
                "records": 0,
                "bytes": 0,
                "extensions": {},
                "ages": {},
                "domains": set(),
                "classifications": set(),
            },
        )
        group["records"] = cast(int, group["records"]) + 1
        group["bytes"] = cast(int, group["bytes"]) + int(row["size_bytes"])
        _increment(group["extensions"], str(row["extension"] or "[none]"))
        _increment(group["ages"], str(row["age"]))
        domain = _object(str(row["security_domain_json"]))
        classification = _object(str(row["classification_json"]))
        assert isinstance(group["domains"], set)
        assert isinstance(group["classifications"], set)
        group["domains"].add(str(domain["domain_id"]))
        group["classifications"].add(str(classification["display_name"]))

    actionable = sorted(
        (
            (key, value)
            for key, value in grouped.items()
            if key[1]
            in {CoverageStatus.MISSING_INGESTION_CAPABILITY, CoverageStatus.UNKNOWN}
        ),
        key=lambda item: (
            -cast(int, item[1]["records"]),
            -cast(int, item[1]["bytes"]),
            -len(cast(dict[str, int], item[1]["extensions"])),
            item[0][0],
        ),
    )
    ranks = {key: rank for rank, (key, _) in enumerate(actionable, 1)}
    opportunities = []
    for key, group in grouped.items():
        category, status, missing = key
        records = cast(int, group["records"])
        size_bytes = cast(int, group["bytes"])
        extensions = _counts(group["extensions"])
        opportunities.append(
            CoverageOpportunity(
                category,
                status,
                records,
                _percentage(records, total_records),
                size_bytes,
                _percentage(size_bytes, total_bytes),
                extensions,
                len(extensions),
                _counts(group["ages"]),
                "local-files.ingest"
                if status is CoverageStatus.SUPPORTED_NOW
                else None,
                missing,
                tuple(sorted(cast(set[str], group["domains"]))),
                tuple(sorted(cast(set[str], group["classifications"]))),
                "low" if status is CoverageStatus.UNKNOWN else "high",
                (
                    "metadata-only; no semantic value was assessed",
                    "coverage reflects the configured scope and exclusions only",
                ),
                ranks.get(key),
            )
        )
    return tuple(
        sorted(
            opportunities,
            key=lambda item: (
                item.coverage_rank is None,
                item.coverage_rank or 0,
                item.status.value,
                item.category,
            ),
        )
    )


def _coverage_status(supported: bool, missing: str | None) -> CoverageStatus:
    if supported:
        return CoverageStatus.SUPPORTED_NOW
    if missing == "executable.prohibited":
        return CoverageStatus.INTENTIONALLY_PROHIBITED
    if missing == "local-files.unsupported.ingest":
        return CoverageStatus.UNKNOWN
    return CoverageStatus.MISSING_INGESTION_CAPABILITY


def _increment(value: object, key: str) -> None:
    assert isinstance(value, dict)
    value[key] = int(value.get(key, 0)) + 1


def _counts(value: object) -> tuple[tuple[str, int], ...]:
    assert isinstance(value, dict)
    return tuple(sorted((str(key), int(count)) for key, count in value.items()))


def _percentage(value: int, total: int) -> float:
    return 0.0 if total == 0 else round(value * 100.0 / total, 4)


def _candidate_values(candidate: FileCandidate) -> tuple[object, ...]:
    return (
        candidate.resource_id,
        candidate.run_id,
        candidate.root_id,
        str(candidate.path),
        candidate.filename,
        candidate.extension,
        candidate.category,
        candidate.mime_type,
        candidate.size_bytes,
        candidate.modified_at.isoformat(),
        None if candidate.created_at is None else candidate.created_at.isoformat(),
        int(candidate.hidden),
        int(candidate.symlink),
        _json(candidate.security_domain.to_dict()),
        _json(candidate.classification.to_dict()),
        candidate.metadata_fingerprint,
        int(candidate.supported_ingestion),
        candidate.missing_capability,
        candidate.state.value,
        _json(list(candidate.warnings)),
        int(candidate.selected),
        None if candidate.record is None else _json(candidate.record.to_dict()),
        candidate.content_hash,
    )


def _row_to_candidate(row: sqlite3.Row) -> FileCandidate:
    record_value = (
        None if row["record_json"] is None else _object(str(row["record_json"]))
    )
    warnings = json.loads(str(row["warnings_json"]))
    if not isinstance(warnings, list) or not all(
        isinstance(item, str) for item in warnings
    ):
        raise ValueError("stored warnings are invalid")
    return FileCandidate(
        str(row["run_id"]),
        str(row["resource_id"]),
        str(row["root_id"]),
        Path(str(row["path"])),
        str(row["filename"]),
        str(row["extension"]),
        str(row["category"]),
        None if row["mime_type"] is None else str(row["mime_type"]),
        int(row["size_bytes"]),
        _datetime(str(row["modified_at"])),
        None if row["created_at"] is None else _datetime(str(row["created_at"])),
        bool(row["hidden"]),
        bool(row["symlink"]),
        SecurityDomain.from_dict(_object(str(row["security_domain_json"]))),
        Classification.from_dict(_object(str(row["classification_json"]))),
        str(row["metadata_fingerprint"]),
        bool(row["supported_ingestion"]),
        None if row["missing_capability"] is None else str(row["missing_capability"]),
        CandidateState(row["state"]),
        tuple(warnings),
        bool(row["selected"]),
        None if record_value is None else UniversalRecordRef.from_dict(record_value),
        None if row["content_hash"] is None else str(row["content_hash"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _object(value: str) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("stored JSON object is invalid")
    return decoded


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
