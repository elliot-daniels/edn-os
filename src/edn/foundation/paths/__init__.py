"""Runtime path validation under the approved data root."""

from __future__ import annotations

from pathlib import Path

from edn.foundation.config.settings import Settings
from edn.foundation.errors import PathValidationError

# Validated runtime paths use the same shape as Settings; no duplicate model.
RuntimePaths = Settings

_VALIDATED_PATH_FIELDS: tuple[str, ...] = (
    "configuration_root",
    "log_root",
    "database_root",
    "attachment_root",
    "source_pst_root",
    "export_root",
    "backup_root",
)


def resolve_runtime_paths(settings: Settings) -> RuntimePaths:
    """Validate that all runtime paths remain beneath ``data_root``.

    Uses resolved canonical paths for comparison. Does not verify volume
    encryption, create directories, or mutate ``settings``.
    """
    data_root = settings.data_root.resolve()
    _ensure_absolute(data_root, "data_root")

    for field in _VALIDATED_PATH_FIELDS:
        runtime_path = getattr(settings, field).resolve()
        _ensure_absolute(runtime_path, field)
        if not _is_under_root(runtime_path, data_root):
            msg = (
                f"Runtime path {field!r} ({runtime_path}) must be under "
                f"data_root ({data_root})."
            )
            raise PathValidationError(msg)

    if not _is_under_root(data_root, data_root):
        msg = f"data_root ({data_root}) is not a valid root path."
        raise PathValidationError(msg)

    return settings


def _ensure_absolute(path: Path, field: str) -> None:
    if not path.is_absolute():
        msg = f"Runtime path {field!r} must be absolute; got {path}."
        raise PathValidationError(msg)


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
