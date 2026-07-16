"""Tests for runtime path validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from edn.foundation.config import Settings, load_settings
from edn.foundation.errors import PathValidationError
from edn.foundation.paths import RuntimePaths, resolve_runtime_paths


def _settings_for_root(data_root: Path, **overrides: Path) -> Settings:
    defaults = {
        "configuration_root": data_root / "Configuration",
        "log_root": data_root / "Logs",
        "database_root": data_root / "Data" / "Databases",
        "attachment_root": data_root / "Data" / "Attachments",
        "source_pst_root": data_root / "Source" / "PST",
        "export_root": data_root / "Exports",
        "backup_root": data_root / "Backups",
    }
    defaults.update(overrides)
    return Settings(data_root=data_root, **defaults)


def test_resolve_valid_runtime_paths(tmp_path: Path) -> None:
    settings = _settings_for_root(tmp_path)
    runtime = resolve_runtime_paths(settings)

    assert runtime is settings
    assert isinstance(runtime, RuntimePaths)


def test_child_outside_data_root_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    outside = tmp_path / "outside"
    settings = _settings_for_root(data_root, log_root=outside)

    with pytest.raises(PathValidationError, match="log_root"):
        resolve_runtime_paths(settings)


def test_traversal_escape_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    settings = _settings_for_root(data_root, export_root=data_root / ".." / "escaped")

    with pytest.raises(PathValidationError, match="export_root"):
        resolve_runtime_paths(settings)


def test_resolve_does_not_create_directories(tmp_path: Path) -> None:
    data_root = tmp_path / "missing-root"
    settings = _settings_for_root(data_root)

    resolve_runtime_paths(settings)

    assert not data_root.exists()


def test_loaded_settings_validate_under_synthetic_root(tmp_path: Path) -> None:
    content = f"""
data_root = "{tmp_path.as_posix()}"
configuration_root = "Configuration"
log_root = "Logs"
database_root = "Data/Databases"
attachment_root = "Data/Attachments"
source_pst_root = "Source/PST"
export_root = "Exports"
backup_root = "Backups"
"""
    config_path = tmp_path / "settings.toml"
    config_path.write_text(content, encoding="utf-8")

    settings = load_settings(config_path)
    resolve_runtime_paths(settings)
