"""POSIX owner-only local intake storage; unsupported platforms fail closed."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID


class IntakeSecurityError(ValueError):
    """Fixed platform/storage diagnostic without request content."""


def require_supported_platform() -> None:
    if (
        os.name != "posix"
        or sys.platform != "linux"
        or not hasattr(os, "geteuid")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise IntakeSecurityError("Protected intake storage requires Linux or WSL")
    try:
        import fcntl

        if not callable(fcntl.flock):
            raise ImportError
    except ImportError:
        raise IntakeSecurityError(
            "Protected intake storage requires Linux or WSL"
        ) from None


def validate_root(root: Path) -> Path:
    require_supported_platform()
    if not root.is_absolute():
        raise IntakeSecurityError("Intake root must be absolute")
    for parent in (root, *root.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise IntakeSecurityError("Intake root ancestry is unsafe")
        if info.st_uid not in {os.geteuid(), 0}:
            raise IntakeSecurityError("Intake root ancestry ownership is unsafe")
        writable = stat.S_IMODE(info.st_mode) & 0o022
        if writable and not (parent != root and info.st_mode & stat.S_ISVTX):
            raise IntakeSecurityError("Intake root ancestry permissions are unsafe")
    current = root.lstat()
    if current.st_uid != os.geteuid() or stat.S_IMODE(current.st_mode) != 0o700:
        raise IntakeSecurityError("Intake root must be owner-only mode 0700")
    return root


def _validate_descriptor(descriptor: int) -> None:
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise IntakeSecurityError(
            "Intake file must be owned regular mode 0600 without links"
        )


def protect_file(path: Path, *, create: bool = False) -> None:
    require_supported_platform()
    validate_root(path.parent)
    flags = os.O_RDWR | os.O_NOFOLLOW
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        _validate_descriptor(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def request_lock(root: Path, request_id: str) -> Iterator[None]:
    require_supported_platform()
    validate_root(root)
    try:
        if str(UUID(request_id)) != request_id:
            raise ValueError
    except (ValueError, AttributeError):
        raise IntakeSecurityError("Invalid request lock identity") from None
    lock = root / (request_id + ".lock")
    try:
        descriptor = os.open(
            lock, os.O_RDWR | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError:
        descriptor = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        _validate_descriptor(descriptor)
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
