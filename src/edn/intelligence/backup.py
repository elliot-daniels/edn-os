"""Allowlisted, integrity-checked local operational backup and restore."""

# ruff: noqa: E501 -- manifest records and safety messages stay explicit.

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1
_PROHIBITED_PARTS = frozenset(
    {"token", "tokens", "secret", "secrets", "credential", "credentials", "raw-graph"}
)


@dataclass(frozen=True, slots=True)
class BackupComponent:
    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_id: str
    created_at: datetime
    schema_version: int
    components: tuple[tuple[str, str, int, str], ...]
    excluded_components: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("backup timestamp must be timezone-aware")
        if self.schema_version != _SCHEMA_VERSION:
            raise ValueError("unsupported backup manifest schema")

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at.isoformat(),
            "schema_version": self.schema_version,
            "components": [
                {
                    "name": name,
                    "sha256": digest,
                    "size_bytes": size,
                    "filename": filename,
                }
                for name, digest, size, filename in self.components
            ],
            "excluded_components": list(self.excluded_components),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BackupManifest:
        if int(value.get("schema_version", -1)) != _SCHEMA_VERSION:
            raise ValueError("unsupported backup manifest schema")
        components = value.get("components")
        if not isinstance(components, list):
            raise ValueError("backup components must be a list")
        return cls(
            str(value["backup_id"]),
            datetime.fromisoformat(str(value["created_at"])),
            int(value["schema_version"]),
            tuple(
                (
                    str(item["name"]),
                    str(item["sha256"]),
                    int(item["size_bytes"]),
                    str(item["filename"]),
                )
                for item in components
            ),
            tuple(str(item) for item in value.get("excluded_components", [])),
        )


class OperationalBackup:
    """Backup only explicitly supplied operational files; never overwrites restore targets."""

    def create(
        self,
        destination: Path,
        *,
        components: tuple[BackupComponent, ...],
        excluded_components: tuple[str, ...] = (
            "secrets",
            "authentication_tokens",
            "raw_graph_payloads",
            "protected_pa005_evidence",
        ),
        now: datetime | None = None,
    ) -> BackupManifest:
        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("backup timestamp must be timezone-aware")
        if destination.exists():
            raise FileExistsError("backup destination must not already exist")
        names = {item.name for item in components}
        if len(names) != len(components):
            raise ValueError("backup component names must be unique")
        for component in components:
            if any(
                prohibited in component.name.casefold()
                for prohibited in _PROHIBITED_PARTS
            ):
                raise PermissionError(
                    "prohibited component names cannot enter operational backup"
                )
            if not component.path.is_file():
                raise FileNotFoundError(component.path)
            if any(
                prohibited in part.casefold()
                for part in component.path.parts
                for prohibited in _PROHIBITED_PARTS
            ):
                raise PermissionError(
                    "prohibited material cannot enter operational backup"
                )
        destination.mkdir(parents=True)
        records: list[tuple[str, str, int, str]] = []
        for component in sorted(components, key=lambda item: item.name):
            filename = f"{len(records):03d}-{component.name}.bin"
            target = destination / filename
            shutil.copyfile(component.path, target)
            digest = _sha256(target)
            records.append((component.name, digest, target.stat().st_size, filename))
        backup_id = (
            "backup-"
            + hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()[
                :24
            ]
        )
        manifest = BackupManifest(
            backup_id, timestamp, _SCHEMA_VERSION, tuple(records), excluded_components
        )
        (destination / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def verify(self, backup: Path) -> BackupManifest:
        manifest_path = backup / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("backup manifest is missing")
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("backup manifest is invalid")
        manifest = BackupManifest.from_dict(value)
        for name, digest, size, filename in manifest.components:
            path = backup / filename
            if (
                not path.is_file()
                or path.stat().st_size != size
                or _sha256(path) != digest
            ):
                raise ValueError(f"backup integrity failed for {name}")
        return manifest

    def restore(self, backup: Path, destination: Path) -> BackupManifest:
        manifest = self.verify(backup)
        if destination.exists():
            raise FileExistsError(
                "restore target exists; live operational state cannot be overwritten"
            )
        destination.mkdir(parents=True)
        for _, _, _, filename in manifest.components:
            shutil.copyfile(backup / filename, destination / filename)
        (destination / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
