"""Generic read-only file fingerprinting."""

from __future__ import annotations

import hashlib
from pathlib import Path

from edn.foundation.errors import PathValidationError, ValidationError

_DEFAULT_CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> str:
    """Return the lowercase SHA-256 hex digest of a regular file.

    Reads incrementally in binary mode. Does not alter or log file content.
    """
    if chunk_size <= 0:
        msg = f"chunk_size must be positive; got {chunk_size}."
        raise ValidationError(msg)

    if not path.exists():
        msg = f"Path does not exist: {path}"
        raise PathValidationError(msg)

    if not path.is_file():
        msg = f"Path is not a regular file: {path}"
        raise PathValidationError(msg)

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        msg = f"Unable to read file: {path}"
        raise PathValidationError(msg) from exc

    return digest.hexdigest()
