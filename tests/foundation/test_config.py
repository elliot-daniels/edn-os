"""Comprehensive tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from edn.foundation.config import Settings, load_settings
from edn.foundation.errors import (
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)


def _write_settings(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _valid_toml(data_root: Path) -> str:
    root = data_root.as_posix()
    return f"""
data_root = "{root}"
configuration_root = "Configuration"
log_root = "Logs"
database_root = "Data/Databases"
attachment_root = "Data/Attachments"
source_pst_root = "Source/PST"
export_root = "Exports"
backup_root = "Backups"
"""


def test_load_valid_configuration(tmp_path: Path) -> None:
    config_path = _write_settings(tmp_path / "settings.toml", _valid_toml(tmp_path))
    settings = load_settings(config_path)

    assert isinstance(settings, Settings)
    assert settings.data_root == tmp_path
    assert settings.log_root == (tmp_path / "Logs").resolve()
    assert settings.database_root == (tmp_path / "Data" / "Databases").resolve()
    assert settings.source_pst_root == (tmp_path / "Source" / "PST").resolve()


def test_load_windows_style_example_parsing(tmp_path: Path) -> None:
    # TOML basic strings treat backslash as escape; use forward slashes on Windows.
    data_root = tmp_path / "EDN OS"
    content = f"""
data_root = "{data_root.as_posix()}"
configuration_root = "Configuration"
log_root = "Logs"
database_root = "Data/Databases"
attachment_root = "Data/Attachments"
source_pst_root = "Source/PST"
export_root = "Exports"
backup_root = "Backups"
"""
    config_path = _write_settings(tmp_path / "settings.toml", content)
    settings = load_settings(config_path)

    assert settings.data_root == data_root
    expected_db = (data_root / "Data" / "Databases").resolve()
    assert settings.database_root == expected_db


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationFileNotFoundError):
        load_settings(tmp_path / "missing.toml")


def test_missing_required_field_raises(tmp_path: Path) -> None:
    content = f'data_root = "{tmp_path.as_posix()}"\nlog_root = "Logs"\n'
    config_path = _write_settings(tmp_path / "settings.toml", content)

    with pytest.raises(ConfigurationValidationError, match="configuration_root"):
        load_settings(config_path)


def test_empty_field_raises(tmp_path: Path) -> None:
    content = _valid_toml(tmp_path).replace('log_root = "Logs"', 'log_root = "   "')
    config_path = _write_settings(tmp_path / "settings.toml", content)

    with pytest.raises(ConfigurationValidationError, match="log_root"):
        load_settings(config_path)


def test_relative_data_root_rejected(tmp_path: Path) -> None:
    content = _valid_toml(Path("relative/root"))
    config_path = _write_settings(tmp_path / "settings.toml", content)

    with pytest.raises(ConfigurationValidationError, match="data_root"):
        load_settings(config_path)


def test_absolute_child_paths_allowed(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    logs = data_root / "Logs"
    content = f"""
data_root = "{data_root.as_posix()}"
configuration_root = "{(data_root / 'Configuration').as_posix()}"
log_root = "{logs.as_posix()}"
database_root = "{(data_root / 'Data/Databases').as_posix()}"
attachment_root = "{(data_root / 'Data/Attachments').as_posix()}"
source_pst_root = "{(data_root / 'Source/PST').as_posix()}"
export_root = "{(data_root / 'Exports').as_posix()}"
backup_root = "{(data_root / 'Backups').as_posix()}"
"""
    config_path = _write_settings(tmp_path / "settings.toml", content)
    settings = load_settings(config_path)

    assert settings.log_root == logs.resolve()


def test_load_does_not_create_directories(tmp_path: Path) -> None:
    data_root = tmp_path / "new-root"
    config_path = _write_settings(tmp_path / "settings.toml", _valid_toml(data_root))

    load_settings(config_path)

    assert not data_root.exists()


def test_invalid_toml_raises(tmp_path: Path) -> None:
    config_path = _write_settings(tmp_path / "settings.toml", "data_root = [invalid")

    with pytest.raises(ConfigurationValidationError, match="Invalid TOML"):
        load_settings(config_path)
