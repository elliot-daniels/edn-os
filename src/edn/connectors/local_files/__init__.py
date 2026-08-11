"""Approved-root Local Files connector."""

from edn.connectors.local_files.catalogue import CandidateCatalogue
from edn.connectors.local_files.config import (
    CONFIG_SCHEMA_VERSION,
    ApprovedRoot,
    LocalFilesConfig,
    SymlinkPolicy,
    load_config,
)
from edn.connectors.local_files.connector import (
    CONNECTOR_ID,
    CONNECTOR_VERSION,
    SUPPORTED_TEXT_EXTENSIONS,
    LocalFilesConnector,
    classify_extension,
)
from edn.connectors.local_files.fingerprint import (
    FileFingerprint,
    FingerprintType,
    content_sha256,
    metadata_fingerprint,
)
from edn.connectors.local_files.models import (
    CandidateState,
    CoverageOpportunity,
    CoverageStatus,
    DiscoverySummary,
    FileCandidate,
    UnsupportedCapabilitySignal,
)

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "CONNECTOR_ID",
    "CONNECTOR_VERSION",
    "SUPPORTED_TEXT_EXTENSIONS",
    "ApprovedRoot",
    "CandidateCatalogue",
    "CandidateState",
    "CoverageOpportunity",
    "CoverageStatus",
    "DiscoverySummary",
    "FileCandidate",
    "FileFingerprint",
    "FingerprintType",
    "LocalFilesConfig",
    "LocalFilesConnector",
    "SymlinkPolicy",
    "UnsupportedCapabilitySignal",
    "classify_extension",
    "content_sha256",
    "load_config",
    "metadata_fingerprint",
]
