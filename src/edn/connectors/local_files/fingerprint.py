"""Explicit tiered fingerprints for Local Files candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FingerprintType(StrEnum):
    PATH_METADATA = "path_metadata"
    METADATA_SHA256 = "metadata_sha256"
    CONTENT_SHA256 = "content_sha256"


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    fingerprint_type: FingerprintType
    value: str


def metadata_fingerprint(path: Path, *, size: int, modified_ns: int) -> FileFingerprint:
    payload = json.dumps(
        {"path": str(path), "size": size, "modified_ns": modified_ns},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return FileFingerprint(
        FingerprintType.METADATA_SHA256, hashlib.sha256(payload).hexdigest()
    )


def content_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> FileFingerprint:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return FileFingerprint(FingerprintType.CONTENT_SHA256, digest.hexdigest())
