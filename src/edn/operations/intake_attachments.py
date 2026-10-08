"""Bounded local originals for manual intake; no upload, extraction or cloud calls."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID, uuid4

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_METADATA_BYTES = 4096
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class IntakeAttachmentError(ValueError):
    """Fixed, source-free errors suitable for local demo UI display."""


def _uuid(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise IntakeAttachmentError("Attachment identity is invalid.") from None
    return value


def _name(value: str) -> str:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise IntakeAttachmentError("Attachment filename is invalid.")
    basename = (
        unicodedata.normalize("NFKC", value).replace("\\", "/").rsplit("/", 1)[-1]
    )
    basename = re.sub(r"[^A-Za-z0-9._ -]", "_", basename).strip(" .")
    if not basename or len(basename) > 160 or basename.startswith("."):
        raise IntakeAttachmentError("Attachment filename is invalid.")
    return basename


def _media(name: str, payload: bytes) -> str:
    suffix = Path(name).suffix.casefold()
    media = MEDIA_TYPES.get(suffix)
    valid = (
        (
            suffix == ".pdf"
            and payload.startswith(b"%PDF-")
            and b"%%EOF" in payload[-1024:]
        )
        or (
            suffix == ".png"
            and payload.startswith(b"\x89PNG\r\n\x1a\n")
            and len(payload) >= 33
            and payload[12:16] == b"IHDR"
            and payload.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
        )
        or (
            suffix in {".jpg", ".jpeg"}
            and payload.startswith(b"\xff\xd8\xff")
            and payload.endswith(b"\xff\xd9")
            and len(payload) >= 8
        )
    )
    if media is None or not valid:
        raise IntakeAttachmentError(
            "Use a PDF, JPEG or PNG file with matching content."
        )
    return media


def _reject_links(path: Path) -> None:
    for candidate in (path.absolute(), *path.absolute().parents):
        try:
            attributes = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attributes.st_mode) or (
            getattr(attributes, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise IntakeAttachmentError("Attachment storage must not contain links.")


def _read_regular(path: Path, limit: int) -> bytes:
    _reject_links(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise IntakeAttachmentError("Attachment storage is invalid.")
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise IntakeAttachmentError("Attachment exceeds the size limit.")
    return payload


@dataclass(frozen=True, slots=True)
class IntakeAttachment:
    attachment_id: str
    request_id: str
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _uuid(self.attachment_id)
        _uuid(self.request_id)
        if _name(self.original_name) != self.original_name:
            raise IntakeAttachmentError("Attachment metadata is invalid.")
        if (
            MEDIA_TYPES.get(Path(self.original_name).suffix.casefold())
            != self.media_type
        ):
            raise IntakeAttachmentError("Attachment metadata is invalid.")
        if (
            type(self.size_bytes) is not int
            or not 1 <= self.size_bytes <= MAX_ATTACHMENT_BYTES
        ):
            raise IntakeAttachmentError("Attachment metadata is invalid.")
        if (
            not isinstance(self.sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None
        ):
            raise IntakeAttachmentError("Attachment metadata is invalid.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntakeAttachmentStore:
    """Persist originals before workflow metadata binding; never overwrite or delete."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._validate_root()
        self.root = root.resolve()

    def _validate_root(self) -> None:
        try:
            if not self.root.is_absolute():
                raise IntakeAttachmentError(
                    "Select an existing attachment storage directory."
                )
            _reject_links(self.root)
            if self.root.resolve() == Path(self.root.anchor) or not self.root.is_dir():
                raise IntakeAttachmentError(
                    "Select an existing attachment storage directory."
                )
            if any(
                (parent / ".git").exists() for parent in (self.root, *self.root.parents)
            ):
                raise IntakeAttachmentError(
                    "Attachment originals must stay outside Git."
                )
        except (OSError, RuntimeError):
            raise IntakeAttachmentError("Attachment storage is unavailable.") from None

    def attach(
        self, request_id: str, filename: str, payload: bytes
    ) -> IntakeAttachment:
        self._validate_root()
        _uuid(request_id)
        original_name = _name(filename)
        if not isinstance(payload, bytes):
            raise IntakeAttachmentError("Attachment content must be bytes.")
        if not 1 <= len(payload) <= MAX_ATTACHMENT_BYTES:
            raise IntakeAttachmentError("Attachment exceeds the size limit.")
        media = _media(original_name, payload)
        record = IntakeAttachment(
            str(uuid4()),
            request_id,
            original_name,
            media,
            len(payload),
            hashlib.sha256(payload).hexdigest(),
        )
        request_path = self.root / request_id
        folder = request_path / record.attachment_id
        try:
            _reject_links(request_path)
            request_path.mkdir(exist_ok=True)
            _reject_links(folder)
            folder.mkdir()
            with (folder / "original.bin").open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Exclusive completed metadata is published only after durable bytes.
            temporary = folder / "metadata.pending"
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(record.to_dict(), sort_keys=True))
                stream.flush()
                os.fsync(stream.fileno())
            if os.name == "nt":
                # Windows rename is atomic and refuses an existing destination.
                os.rename(temporary, folder / "metadata.json")
            else:
                os.link(temporary, folder / "metadata.json")
                temporary.unlink()
        except OSError:
            raise IntakeAttachmentError("Attachment could not be stored.") from None
        return record

    def attach_stream(
        self, request_id: str, filename: str, stream: BinaryIO
    ) -> IntakeAttachment:
        """For ordinary file/BytesIO uploads, request no more than cap+one bytes."""
        try:
            payload = stream.read(MAX_ATTACHMENT_BYTES + 1)
        except (OSError, ValueError):
            raise IntakeAttachmentError(
                "Attachment content could not be read."
            ) from None
        return self.attach(request_id, filename, payload)

    def get(self, request_id: str, attachment_id: str) -> IntakeAttachment:
        self._validate_root()
        _uuid(request_id)
        _uuid(attachment_id)
        path = self.root / request_id / attachment_id / "metadata.json"
        try:
            value = json.loads(_read_regular(path, MAX_METADATA_BYTES))
            if not isinstance(value, dict) or set(value) != {
                "attachment_id",
                "request_id",
                "original_name",
                "media_type",
                "size_bytes",
                "sha256",
            }:
                raise ValueError
            record = IntakeAttachment(**value)
            if (record.request_id, record.attachment_id) != (request_id, attachment_id):
                raise ValueError
        except (OSError, ValueError, TypeError, RecursionError):
            raise IntakeAttachmentError(
                "Attachment metadata is unavailable or invalid."
            ) from None
        return record

    def read(self, request_id: str, attachment_id: str) -> bytes:
        record = self.get(request_id, attachment_id)
        path = self.root / request_id / attachment_id / "original.bin"
        try:
            payload = _read_regular(path, MAX_ATTACHMENT_BYTES)
        except (OSError, ValueError):
            raise IntakeAttachmentError(
                "Attachment original is unavailable or invalid."
            ) from None
        if (
            len(payload) != record.size_bytes
            or hashlib.sha256(payload).hexdigest() != record.sha256
        ):
            raise IntakeAttachmentError(
                "Attachment original failed its integrity check."
            )
        _media(record.original_name, payload)
        return payload
