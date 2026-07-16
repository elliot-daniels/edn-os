"""Read-only TOML configuration loading."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from edn.foundation.config.settings import Settings
from edn.foundation.errors import (
    ConfigurationFileNotFoundError,
    ConfigurationValidationError,
)

_REQUIRED_KEYS: tuple[str, ...] = (
    "data_root",
    "configuration_root",
    "log_root",
    "database_root",
    "attachment_root",
    "source_pst_root",
    "export_root",
    "backup_root",
)

_CHILD_KEYS: tuple[str, ...] = _REQUIRED_KEYS[1:]


def load_settings(path: Path) -> Settings:
    """Load and validate settings from a TOML file.

    Opens the file read-only. Does not create directories, log contents,
    or make network calls.
    """
    if not path.is_file():
        msg = f"Configuration file not found: {path}"
        raise ConfigurationFileNotFoundError(msg)

    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Invalid TOML in configuration file {path}: {exc}"
        raise ConfigurationValidationError(msg) from exc

    if not isinstance(raw, dict):
        msg = "Configuration root must be a TOML table."
        raise ConfigurationValidationError(msg)

    _validate_required_keys(raw, path)
    data_root = _parse_data_root(raw["data_root"], path)

    child_paths = {
        key: _parse_child_path(raw[key], key, data_root, path) for key in _CHILD_KEYS
    }

    return Settings(data_root=data_root, **child_paths)


def _validate_required_keys(raw: dict[str, Any], path: Path) -> None:
    for key in _REQUIRED_KEYS:
        if key not in raw:
            msg = f"Missing required configuration key {key!r} in {path}."
            raise ConfigurationValidationError(msg)


def _parse_data_root(value: Any, path: Path) -> Path:
    text = _non_empty_string(value, "data_root", path)
    data_root = Path(text)
    if not data_root.is_absolute():
        msg = (
            f"Configuration key 'data_root' must be an absolute path in {path}; "
            f"got {text!r}."
        )
        raise ConfigurationValidationError(msg)
    return data_root


def _parse_child_path(value: Any, key: str, data_root: Path, path: Path) -> Path:
    text = _non_empty_string(value, key, path)
    child = Path(text)
    if child.is_absolute():
        return child
    return (data_root / child).resolve()


def _non_empty_string(value: Any, key: str, path: Path) -> str:
    if not isinstance(value, str):
        msg = f"Configuration key {key!r} must be a string in {path}."
        raise ConfigurationValidationError(msg)
    if not value.strip():
        msg = f"Configuration key {key!r} must not be empty in {path}."
        raise ConfigurationValidationError(msg)
    return value.strip()
