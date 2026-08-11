"""Local Files candidate, summary, and unsupported-capability models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from edn.core import Classification, SecurityDomain, UniversalRecordRef


class CandidateState(StrEnum):
    DISCOVERED = "discovered"
    UNSUPPORTED = "unsupported"
    INGESTED = "ingested"
    SOURCE_CHANGED = "source_changed"
    INACCESSIBLE = "inaccessible"


@dataclass(frozen=True, slots=True)
class FileCandidate:
    run_id: str
    resource_id: str
    root_id: str
    path: Path
    filename: str
    extension: str
    category: str
    mime_type: str | None
    size_bytes: int
    modified_at: datetime
    created_at: datetime | None
    hidden: bool
    symlink: bool
    security_domain: SecurityDomain
    classification: Classification
    metadata_fingerprint: str
    supported_ingestion: bool
    missing_capability: str | None
    state: CandidateState
    warnings: tuple[str, ...] = ()
    selected: bool = False
    record: UniversalRecordRef | None = None
    content_hash: str | None = None


@dataclass(frozen=True, slots=True)
class UnsupportedCapabilitySignal:
    category: str
    file_count: int
    total_size_bytes: int
    missing_capability: str


class CoverageStatus(StrEnum):
    SUPPORTED_NOW = "supported_now"
    MISSING_INGESTION_CAPABILITY = "missing_ingestion_capability"
    INTENTIONALLY_PROHIBITED = "intentionally_prohibited"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CoverageOpportunity:
    category: str
    status: CoverageStatus
    record_count: int
    record_percentage: float
    total_size_bytes: int
    byte_percentage: float
    extension_counts: tuple[tuple[str, int], ...]
    extension_diversity: int
    recency_counts: tuple[tuple[str, int], ...]
    existing_capability: str | None
    missing_capability: str | None
    security_domains: tuple[str, ...]
    classifications: tuple[str, ...]
    deterministic_confidence: str
    limitations: tuple[str, ...]
    coverage_rank: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoverySummary:
    run_id: str
    approved_roots_scanned: int
    files_discovered: int
    already_known: int
    potentially_ingestible: int
    unsupported: int
    excluded: int
    warnings: int
    total_size_bytes: int
    category_counts: tuple[tuple[str, int], ...]
    extension_counts: tuple[tuple[str, int], ...]
    age_counts: tuple[tuple[str, int], ...]
    unsupported_capabilities: tuple[UnsupportedCapabilitySignal, ...]
    coverage_opportunities: tuple[CoverageOpportunity, ...] = ()
