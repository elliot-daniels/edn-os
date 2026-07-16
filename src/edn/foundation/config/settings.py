"""Immutable typed application settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Authoritative typed configuration for EDN OS runtime paths."""

    data_root: Path
    configuration_root: Path
    log_root: Path
    database_root: Path
    attachment_root: Path
    source_pst_root: Path
    export_root: Path
    backup_root: Path
