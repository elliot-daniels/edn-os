"""Strict tenant-supplied Local Files configuration and root enforcement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from edn.core import Classification, SecurityDomain
from edn.core.security import validate_identifier

CONFIG_SCHEMA_VERSION = "1.0.0"


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
        if self.path == Path(self.path.anchor):
            raise ValueError("filesystem roots are too broad to approve")


@dataclass(frozen=True, slots=True)
class LocalFilesConfig:
    roots: tuple[ApprovedRoot, ...]
    catalogue_path: Path
    content_store_path: Path
    job_store_path: Path | None = None
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
    schema_version: str = CONFIG_SCHEMA_VERSION
    configuration_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != CONFIG_SCHEMA_VERSION:
            raise ValueError("unsupported Local Files configuration schema version")
        if not self.roots:
            raise ValueError("at least one approved root is required")
        identifiers = [root.root_id for root in self.roots]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("approved root IDs must be unique")
        storage_paths = (self.catalogue_path, self.content_store_path) + (
            () if self.job_store_path is None else (self.job_store_path,)
        )
        if any(not path.is_absolute() for path in storage_paths):
            raise ValueError(
                "catalogue, content-store, and job-store paths must be absolute"
            )
        if any(
            _is_within(storage, root.path)
            for storage in storage_paths
            for root in self.roots
        ):
            raise ValueError(
                "catalogue/content/job storage must be outside approved roots"
            )
        self._validate_non_overlapping_roots()
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
        if (
            self.symlink_policy is SymlinkPolicy.WITHIN_ROOT
            and not self.stay_on_filesystem
        ):
            raise ValueError("within-root symlinks require same-filesystem enforcement")
        if not self.metadata_only_discovery:
            raise ValueError("Local Files v0.1 requires metadata-only discovery")
        object.__setattr__(self, "configuration_hash", self._calculate_hash())

    def _validate_non_overlapping_roots(self) -> None:
        for index, left in enumerate(self.roots):
            for right in self.roots[index + 1 :]:
                if _is_within(left.path, right.path) or _is_within(
                    right.path, left.path
                ):
                    raise ValueError("approved roots must not overlap")

    def _calculate_hash(self) -> str:
        value = {
            "schema_version": self.schema_version,
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
            "job_store_path": None
            if self.job_store_path is None
            else str(self.job_store_path),
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


def load_config(
    path: str | Path,
    *,
    repository_root: Path | None = None,
    allow_repository_storage: bool = False,
) -> LocalFilesConfig:
    """Load one strict JSON configuration; unknown fields and types fail closed."""
    config_path = Path(path)
    try:
        decoded: object = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "Local Files configuration could not be read as JSON"
        ) from error
    data = _object(decoded, "configuration")
    allowed = {
        "schema_version",
        "roots",
        "catalogue_path",
        "content_store_path",
        "job_store_path",
        "excluded_roots",
        "allowed_extensions",
        "excluded_extensions",
        "max_file_size_bytes",
        "max_depth",
        "discover_hidden",
        "symlink_policy",
        "stay_on_filesystem",
        "metadata_only_discovery",
        "discovery_batch_size",
        "ingestion_batch_size",
    }
    _reject_unknown(data, allowed, "configuration")
    if data.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(
            "unsupported or missing Local Files configuration schema version"
        )
    roots_value = data.get("roots")
    if not isinstance(roots_value, list):
        raise ValueError("roots must be a list")
    roots = tuple(_load_root(item) for item in roots_value)
    config = LocalFilesConfig(
        roots=roots,
        catalogue_path=_absolute_path(data.get("catalogue_path"), "catalogue_path"),
        content_store_path=_absolute_path(
            data.get("content_store_path"), "content_store_path"
        ),
        job_store_path=_optional_absolute_path(
            data.get("job_store_path"), "job_store_path"
        ),
        excluded_roots=tuple(
            _absolute_path(item, "excluded_roots")
            for item in _list(data.get("excluded_roots", []), "excluded_roots")
        ),
        allowed_extensions=frozenset(
            _strings(data.get("allowed_extensions", []), "allowed_extensions")
        ),
        excluded_extensions=frozenset(
            _strings(data.get("excluded_extensions", []), "excluded_extensions")
        ),
        max_file_size_bytes=_integer(
            data.get("max_file_size_bytes", 10 * 1024 * 1024), "max_file_size_bytes"
        ),
        max_depth=_optional_integer(data.get("max_depth"), "max_depth"),
        discover_hidden=_boolean(data.get("discover_hidden", False), "discover_hidden"),
        symlink_policy=SymlinkPolicy(str(data.get("symlink_policy", "never"))),
        stay_on_filesystem=_boolean(
            data.get("stay_on_filesystem", True), "stay_on_filesystem"
        ),
        metadata_only_discovery=_boolean(
            data.get("metadata_only_discovery", True), "metadata_only_discovery"
        ),
        discovery_batch_size=_integer(
            data.get("discovery_batch_size", 250), "discovery_batch_size"
        ),
        ingestion_batch_size=_integer(
            data.get("ingestion_batch_size", 50), "ingestion_batch_size"
        ),
    )
    detected_repository = repository_root or _find_repository_root(
        config_path.resolve(strict=False)
    )
    if detected_repository is not None and not allow_repository_storage:
        repository = detected_repository.resolve(strict=False)
        for storage in (
            config.catalogue_path,
            config.content_store_path,
            config.job_store_path,
        ):
            if storage is not None and _is_within(storage, repository):
                raise ValueError(
                    "catalogue/content/job storage must remain outside the repository"
                )
    return config


def _find_repository_root(config_path: Path) -> Path | None:
    candidates = (
        Path.cwd(),
        *Path.cwd().parents,
        config_path.parent,
        *config_path.parents,
    )
    for candidate in candidates:
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _load_root(value: object) -> ApprovedRoot:
    data = _object(value, "root")
    _reject_unknown(
        data, {"root_id", "path", "security_domain", "classification"}, "root"
    )
    return ApprovedRoot(
        str(data["root_id"]),
        _absolute_path(data.get("path"), "root.path"),
        SecurityDomain.from_dict(
            _object(data.get("security_domain"), "security_domain")
        ),
        Classification.from_dict(_object(data.get("classification"), "classification")),
    )


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _reject_unknown(data: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(
            f"{name} contains unknown fields: {', '.join(sorted(unknown))}"
        )


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _strings(value: object, name: str) -> tuple[str, ...]:
    items = _list(value, name)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{name} must contain only strings")
    return tuple(cast(list[str], items))


def _absolute_path(value: object, name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty path string")
    result = Path(value)
    if not result.is_absolute():
        raise ValueError(f"{name} must be absolute")
    return result


def _optional_absolute_path(value: object, name: str) -> Path | None:
    return None if value is None else _absolute_path(value, name)


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return value


def _optional_integer(value: object, name: str) -> int | None:
    return None if value is None else _integer(value, name)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True
