"""Tenant-supplied Local Files configuration and approved-root enforcement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from edn.core import Classification, SecurityDomain
from edn.core.security import validate_identifier


class SymlinkPolicy(StrEnum):
    NEVER = "never"
    WITHIN_ROOT = "within_root"


@dataclass(frozen=True, slots=True)
class ApprovedRoot:
    root_id: str
    path: Path
    security_domain: SecurityDomain
    classification: Classification

    def __post_init__(self) -> None:
        validate_identifier(self.root_id, "root_id")
        if not self.path.is_absolute():
            raise ValueError("approved root must be absolute")


@dataclass(frozen=True, slots=True)
class LocalFilesConfig:
    roots: tuple[ApprovedRoot, ...]
    catalogue_path: Path
    content_store_path: Path
    excluded_roots: tuple[Path, ...] = ()
    allowed_extensions: frozenset[str] = frozenset()
    excluded_extensions: frozenset[str] = frozenset()
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_depth: int | None = None
    discover_hidden: bool = False
    symlink_policy: SymlinkPolicy = SymlinkPolicy.NEVER
    stay_on_filesystem: bool = True
    metadata_only_discovery: bool = True
    discovery_batch_size: int = 250
    ingestion_batch_size: int = 50
    configuration_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.roots:
            raise ValueError("at least one approved root is required")
        identifiers = [root.root_id for root in self.roots]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("approved root IDs must be unique")
        if (
            not self.catalogue_path.is_absolute()
            or not self.content_store_path.is_absolute()
        ):
            raise ValueError("catalogue and content-store paths must be absolute")
        if self.max_file_size_bytes < 1:
            raise ValueError("max_file_size_bytes must be positive")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must not be negative")
        if self.discovery_batch_size < 1 or self.ingestion_batch_size < 1:
            raise ValueError("batch sizes must be positive")
        for extension in self.allowed_extensions | self.excluded_extensions:
            if not extension.startswith(".") or extension != extension.casefold():
                raise ValueError("extensions must be lowercase and begin with a dot")
        if self.allowed_extensions & self.excluded_extensions:
            raise ValueError("an extension cannot be both allowed and excluded")
        for excluded in self.excluded_roots:
            if not excluded.is_absolute():
                raise ValueError("excluded roots must be absolute")
            if not any(_is_within(excluded, root.path) for root in self.roots):
                raise ValueError("excluded root must be within an approved root")
        object.__setattr__(self, "configuration_hash", self._calculate_hash())

    def _calculate_hash(self) -> str:
        value = {
            "roots": [
                {
                    "root_id": item.root_id,
                    "path": str(item.path),
                    "domain": item.security_domain.to_dict(),
                    "classification": item.classification.to_dict(),
                }
                for item in sorted(self.roots, key=lambda item: item.root_id)
            ],
            "catalogue_path": str(self.catalogue_path),
            "content_store_path": str(self.content_store_path),
            "excluded_roots": sorted(str(item) for item in self.excluded_roots),
            "allowed_extensions": sorted(self.allowed_extensions),
            "excluded_extensions": sorted(self.excluded_extensions),
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_depth": self.max_depth,
            "discover_hidden": self.discover_hidden,
            "symlink_policy": self.symlink_policy.value,
            "stay_on_filesystem": self.stay_on_filesystem,
            "metadata_only_discovery": self.metadata_only_discovery,
            "discovery_batch_size": self.discovery_batch_size,
            "ingestion_batch_size": self.ingestion_batch_size,
        }
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def root(self, root_id: str) -> ApprovedRoot:
        try:
            return next(item for item in self.roots if item.root_id == root_id)
        except StopIteration as error:
            raise ValueError("scope references an unapproved root") from error

    def validate_candidate_path(self, path: Path, root_id: str) -> Path:
        root = self.root(root_id)
        root_resolved = root.path.resolve(strict=True)
        candidate = path.resolve(strict=True)
        if not _is_within(candidate, root_resolved):
            raise ValueError("path escapes its approved root")
        if any(
            _is_within(candidate, item.resolve(strict=False))
            for item in self.excluded_roots
        ):
            raise ValueError("path is within an excluded root")
        return candidate


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True
