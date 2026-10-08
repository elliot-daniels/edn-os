"""POSIX owner-only local intake storage; unsupported platforms fail closed."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
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


class AnchoredDirectory:
    """All descendant operations remain relative to an owned open directory FD."""

    def __init__(self, root: Path) -> None:
        require_supported_platform()
        if not root.is_absolute():
            raise IntakeSecurityError("Intake root must be absolute")
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in root.parts[1:]:
                info = os.fstat(descriptor)
                if info.st_uid not in {os.geteuid(), 0} or (
                    stat.S_IMODE(info.st_mode) & 0o022
                    and not info.st_mode & stat.S_ISVTX
                ):
                    raise IntakeSecurityError("Intake root ancestry is unsafe")
                following = os.open(
                    self._name(component),
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = following
            self._check_directory(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        self.fd = descriptor

    @classmethod
    def _from_fd(cls, descriptor: int) -> AnchoredDirectory:
        result = object.__new__(cls)
        result.fd = descriptor
        try:
            cls._check_directory(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        return result

    @staticmethod
    def _check_directory(descriptor: int) -> None:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise IntakeSecurityError("Anchored intake directory is unsafe")

    @staticmethod
    def _name(name: str) -> str:
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or "\x00" in name
        ):
            raise IntakeSecurityError("Invalid anchored file name")
        return name

    def child(self, name: str, *, create: bool = False) -> AnchoredDirectory:
        name = self._name(name)
        if create:
            with suppress(FileExistsError):
                os.mkdir(name, 0o700, dir_fd=self.fd)
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd
        )
        return self._from_fd(descriptor)

    def open_file(self, name: str, *, create: bool = False, write: bool = False) -> int:
        name = self._name(name)
        flags = (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW
        if create:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(name, flags, 0o600, dir_fd=self.fd)
        try:
            _validate_descriptor(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    def exists(self, name: str) -> bool:
        try:
            os.stat(self._name(name), dir_fd=self.fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def replace(self, source: str, target: str) -> None:
        os.replace(
            self._name(source),
            self._name(target),
            src_dir_fd=self.fd,
            dst_dir_fd=self.fd,
        )

    def publish(self, source: str, target: str) -> None:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise IntakeSecurityError("Safe no-clobber publication is unavailable")
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        if (
            rename(
                self.fd,
                os.fsencode(self._name(source)),
                self.fd,
                os.fsencode(self._name(target)),
                1,
            )
            != 0
        ):
            error = ctypes.get_errno()
            raise OSError(error, "Safe intake publication failed")

    def unlink(self, name: str) -> None:
        os.unlink(self._name(name), dir_fd=self.fd)

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        try:
            descriptor = self.open_file(name, create=True, write=True)
        except FileExistsError:
            descriptor = self.open_file(name, write=True)
        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> AnchoredDirectory:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def verify_evidence(
    root: Path, request_id: str, manifest: tuple[dict[str, object], ...]
) -> None:
    """Require completed quota receipts and exact persisted evidence bytes."""
    import hashlib
    import json

    try:
        if str(UUID(request_id)) != request_id:
            raise ValueError
        with (
            AnchoredDirectory(root) as directory,
            directory.child(request_id) as request,
        ):
            receipt_fd = request.open_file("attachments.json")
            with os.fdopen(receipt_fd, "rb") as stream:
                receipt = json.loads(stream.read(65537))
            if (
                set(receipt) != {"schema_version", "request_id", "entries"}
                or receipt["schema_version"] != 1
                or receipt["request_id"] != request_id
            ):
                raise ValueError
            entries = receipt["entries"]
            if not isinstance(entries, list) or len(entries) > 100:
                raise ValueError
            total = 0
            complete = {}
            for entry in entries:
                if (
                    set(entry) != {"attachment_id", "size_bytes", "state"}
                    or str(UUID(entry["attachment_id"])) != entry["attachment_id"]
                    or type(entry["size_bytes"]) is not int
                    or not 0 < entry["size_bytes"] <= 20_000_000
                    or entry["state"] not in {"reserved", "complete"}
                ):
                    raise ValueError
                if entry["attachment_id"] in complete:
                    raise ValueError
                complete[entry["attachment_id"]] = entry
                total += entry["size_bytes"]
            if total > 100_000_000:
                raise ValueError
            for metadata in manifest:
                attachment_id = metadata["attachment_id"]
                if (
                    not isinstance(attachment_id, str)
                    or metadata["request_id"] != request_id
                ):
                    raise ValueError
                entry = complete.get(attachment_id)
                if (
                    entry is None
                    or entry["state"] != "complete"
                    or entry["size_bytes"] != metadata["size_bytes"]
                ):
                    raise ValueError
                with request.child(attachment_id) as attachment:
                    fd = attachment.open_file("metadata.json")
                    with os.fdopen(fd, "rb") as stream:
                        stored = json.loads(stream.read(65537))
                    if stored != metadata:
                        raise ValueError
                    fd = attachment.open_file("original.bin")
                    with os.fdopen(fd, "rb") as stream:
                        payload = stream.read(20_000_001)
                    media = metadata["media_type"]
                    valid_format = (
                        (media == "application/pdf" and payload.startswith(b"%PDF-"))
                        or (
                            media == "image/png"
                            and payload.startswith(b"\x89PNG\r\n\x1a\n")
                        )
                        or (
                            media == "image/jpeg"
                            and payload.startswith(b"\xff\xd8\xff")
                            and payload.endswith(b"\xff\xd9")
                        )
                    )
                    if not valid_format:
                        raise ValueError
                    if (
                        len(payload) != metadata["size_bytes"]
                        or hashlib.sha256(payload).hexdigest() != metadata["sha256"]
                    ):
                        raise ValueError
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise IntakeSecurityError(
            "Stored request evidence is unavailable or invalid"
        ) from None
