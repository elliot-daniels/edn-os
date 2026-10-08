"""Allowlisted, integrity-checked local operational backup and restore."""

# ruff: noqa: E501 -- manifest records and safety messages stay explicit.

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

_SCHEMA_VERSION = 1
_SQLITE_HEADER = b"SQLite format 3\x00"
_SQLITE_SNAPSHOT_SECONDS = 30.0
_PROHIBITED_PARTS = frozenset(
    {"token", "tokens", "secret", "secrets", "credential", "credentials", "raw-graph"}
)


@dataclass(frozen=True, slots=True)
class BackupComponent:
    name: str
    path: Path
    sqlite_snapshot: bool = False

    def __post_init__(self) -> None:
        if type(self.sqlite_snapshot) is not bool:
            raise ValueError("SQLite snapshot selection must be a boolean")


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
        names: set[str] = set()
        filenames: set[str] = set()
        for name, digest, size, filename in self.components:
            _validate_name(name)
            _validate_filename(filename)
            if name.casefold() in names or filename.casefold() in filenames:
                raise ValueError("backup components must have unique names and filenames")
            names.add(name.casefold())
            filenames.add(filename.casefold())
            if size < 0 or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("invalid backup integrity metadata")

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
        if type(value.get("schema_version")) is not int or value["schema_version"] != _SCHEMA_VERSION:
            raise ValueError("unsupported backup manifest schema")
        components = value.get("components")
        if not isinstance(components, list):
            raise ValueError("backup components must be a list")
        if not isinstance(value.get("backup_id"), str) or not isinstance(value.get("created_at"), str):
            raise ValueError("backup identity and timestamp must be strings")
        excluded = value.get("excluded_components", [])
        if not isinstance(excluded, list) or any(not isinstance(item, str) for item in excluded):
            raise ValueError("backup exclusions must be strings")
        for item in components:
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in ("name", "sha256", "filename")) or type(item.get("size_bytes")) is not int:
                raise ValueError("invalid backup component metadata types")
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
        _reject_links(destination)
        if destination.exists():
            raise FileExistsError("backup destination must not already exist")
        names = {item.name.casefold() for item in components}
        if len(names) != len(components):
            raise ValueError("backup component names must be unique")
        for component in components:
            _validate_name(component.name)
            _reject_links(component.path)
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
            with _open_regular(component.path) as stream:
                sqlite_header = stream.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER
            if sqlite_header and not component.sqlite_snapshot:
                raise ValueError("SQLite components require explicit consistent snapshot mode")
            if component.sqlite_snapshot and not sqlite_header:
                raise ValueError("SQLite snapshot requires a SQLite database")
            if component.sqlite_snapshot:
                _reject_sqlite_links(component.path)
        destination.mkdir(parents=True)
        records: list[tuple[str, str, int, str]] = []
        for component in sorted(components, key=lambda item: item.name):
            filename = f"{len(records):03d}-{component.name}.bin"
            target = destination / filename
            if component.sqlite_snapshot:
                _sqlite_snapshot(component.path, target)
            else:
                _copy_exclusive(component.path, target, reject_sqlite=True)
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
        _publish_manifest(destination, manifest)
        return manifest

    def verify(self, backup: Path) -> BackupManifest:
        _reject_links(backup)
        manifest_path = backup / "manifest.json"
        _reject_links(manifest_path)
        if not manifest_path.is_file():
            raise ValueError("backup manifest is missing")
        with _open_regular(manifest_path) as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("backup manifest is invalid")
        manifest = BackupManifest.from_dict(value)
        for name, digest, size, filename in manifest.components:
            path = backup / filename
            _reject_links(path)
            if (
                not path.is_file()
                or path.stat().st_size != size
                or _sha256(path) != digest
            ):
                raise ValueError(f"backup integrity failed for {name}")
        return manifest

    def restore(self, backup: Path, destination: Path) -> BackupManifest:
        manifest = self.verify(backup)
        _reject_links(destination)
        if destination.exists():
            raise FileExistsError(
                "restore target exists; live operational state cannot be overwritten"
            )
        destination.mkdir(parents=True)
        for name, digest, size, filename in manifest.components:
            target = destination / filename
            _copy_exclusive(backup / filename, target)
            if target.stat().st_size != size or _sha256(target) != digest:
                raise ValueError(f"backup integrity failed during restore for {name}")
        _publish_manifest(destination, manifest)
        return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with _open_regular(path) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_name(name: str) -> None:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name) is None:
        raise ValueError("backup component name must be a portable identifier")
    if any(part in name.casefold() for part in _PROHIBITED_PARTS):
        raise PermissionError("prohibited component names cannot enter operational backup")


def _validate_filename(filename: str) -> None:
    # A portable basename excludes both POSIX and Windows traversal, drives,
    # UNC paths, alternate data streams and the reserved manifest destination.
    if re.fullmatch(r"[0-9]{3,}-[A-Za-z0-9][A-Za-z0-9_-]*\.bin", filename) is None:
        raise ValueError("backup component filename must be a portable basename")


def _reject_links(path: Path) -> None:
    for candidate in (path.absolute(), *path.absolute().parents):
        try:
            attributes = candidate.lstat()
        except FileNotFoundError:
            attributes = None
        if (attributes is not None and getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) or candidate.is_symlink() or (
            hasattr(candidate, "is_junction") and candidate.is_junction()
        ):
            raise ValueError("backup paths must not contain symlinks or junctions")


def _copy_exclusive(source: Path, target: Path, *, reject_sqlite: bool = False) -> None:
    _reject_links(source)
    _reject_links(target)
    with _open_regular(source) as incoming:
        header = incoming.read(len(_SQLITE_HEADER))
        if reject_sqlite and header == _SQLITE_HEADER:
            raise ValueError("SQLite components require explicit consistent snapshot mode")
        with target.open("xb") as outgoing:
            outgoing.write(header)
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(block)


def _reject_sqlite_links(path: Path) -> None:
    _reject_links(path)
    for suffix in ("-wal", "-shm", "-journal"):
        _reject_links(Path(str(path) + suffix))


def _sqlite_snapshot(source: Path, target: Path) -> None:
    _reject_sqlite_links(source)
    _reject_sqlite_links(target)
    with _open_regular(source) as stream:
        if stream.read(len(_SQLITE_HEADER)) != _SQLITE_HEADER:
            raise ValueError("SQLite snapshot requires a SQLite database")
    # Reserve our new component before SQLite opens it in existing-file mode.
    with target.open("xb"):
        pass
    deadline = time.monotonic() + _SQLITE_SNAPSHOT_SECONDS

    def check_deadline(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("SQLite snapshot exceeded its time bound")

    try:
        with (
            closing(sqlite3.connect(
                f"{source.absolute().as_uri()}?mode=ro", uri=True, timeout=0.1
            )) as incoming,
            closing(sqlite3.connect(
                f"{target.absolute().as_uri()}?mode=rw", uri=True, timeout=0.1
            )) as outgoing,
        ):
            incoming.backup(outgoing, pages=128, progress=check_deadline, sleep=0.05)
            check_deadline(0, 0, 0)
            outgoing.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            # Normalize only the new snapshot, so restore needs no WAL sidecars.
            if outgoing.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise ValueError("SQLite snapshot could not become self-contained")
            if outgoing.execute("PRAGMA quick_check(1)").fetchall() != [("ok",)]:
                raise ValueError("SQLite snapshot integrity failed")
            check_deadline(0, 0, 0)
    except sqlite3.Error:
        raise ValueError("SQLite snapshot failed safely") from None


def _open_regular(path: Path) -> BinaryIO:
    _reject_links(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError("backup components must be regular files")
    return os.fdopen(descriptor, "rb")


def _publish_manifest(destination: Path, manifest: BackupManifest) -> None:
    # Hard-link publication is atomic and refuses an existing completion marker.
    # No partially written JSON can ever appear at the manifest filename.
    descriptor, temporary = tempfile.mkstemp(prefix=".manifest-", dir=destination)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination / "manifest.json")
    finally:
        Path(temporary).unlink()
