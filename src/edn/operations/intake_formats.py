"""Single bounded six-format codec for local intake evidence and backend approval."""

from __future__ import annotations

import io
import re
import stat
import unicodedata
import zlib
from collections.abc import Iterator
from email import policy
from email.parser import BytesHeaderParser
from pathlib import Path, PurePosixPath
from typing import cast
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

MAX_ATTACHMENT_BYTES = 20_000_000
MAX_REQUEST_BYTES = 100_000_000
MAX_REQUEST_FILES = 100
MAX_METADATA_BYTES = 65_536
MAX_DOCX_ENTRIES = 2000
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".eml": "message/rfc822",
    ".txt": "text/plain",
}


class IntakeAttachmentError(ValueError):
    """Fixed source-free errors suitable for local intake UI display."""


def normalize_attachment_name(value: str) -> str:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise IntakeAttachmentError("Attachment filename is invalid.")
    basename = (
        unicodedata.normalize("NFKC", value).replace("\\", "/").rsplit("/", 1)[-1]
    )
    basename = re.sub(r"[^A-Za-z0-9._ -]", "_", basename).strip(" .")
    if not basename or len(basename) > 160 or basename.startswith("."):
        raise IntakeAttachmentError("Attachment filename is invalid.")
    return basename


def _text(payload: bytes) -> str:
    try:
        value = payload.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise IntakeAttachmentError("Attachment text must be valid UTF-8.") from None
    if any(ord(c) < 32 and c not in "\t\r\n" for c in value):
        raise IntakeAttachmentError(
            "Attachment text contains unsupported control bytes."
        )
    return value


def _docx(payload: bytes) -> None:
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_DOCX_ENTRIES:
                raise ValueError
            expanded = 0
            names: set[str] = set()
            for entry in entries:
                name = entry.orig_filename
                parts = name.rstrip("/").split("/")
                mode = entry.external_attr >> 16
                expanded += entry.file_size
                if (
                    not name
                    or "\\" in name
                    or ":" in name
                    or "\x00" in name
                    or PurePosixPath(name).is_absolute()
                    or any(part in {"", ".", ".."} for part in parts)
                    or name.casefold() in names
                    or entry.flag_bits & 1
                    or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                    or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})
                    or expanded > MAX_ATTACHMENT_BYTES
                    or entry.file_size > max(entry.compress_size, 1) * 100
                    or "vbaproject" in name.casefold()
                ):
                    raise ValueError
                names.add(name.casefold())
                if not entry.is_dir():
                    with archive.open(entry) as incoming:
                        content = incoming.read(entry.file_size + 1)
                    if len(content) != entry.file_size:
                        raise ValueError
            for name, expected in (
                (
                    "[Content_Types].xml",
                    "{http://schemas.openxmlformats.org/package/2006/content-types}Types",
                ),
                (
                    "word/document.xml",
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document",
                ),
            ):
                content = archive.read(name)
                if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
                    raise ValueError
                _validate_xml(content, expected)
    except (
        BadZipFile,
        KeyError,
        ValueError,
        RuntimeError,
        OSError,
        ElementTree.ParseError,
        zlib.error,
    ):
        raise IntakeAttachmentError(
            "DOCX structure exceeds limits or is unsupported."
        ) from None


def _validate_xml(content: bytes, expected: str) -> None:
    # Strict XML text prevents UTF-16/NUL encodings bypassing DTD/entity guards.
    text = content.decode("utf-8-sig", errors="strict")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError
    parser: ElementTree.XMLPullParser[ElementTree.Element] = ElementTree.XMLPullParser(
        events=("start", "end")
    )
    nodes = depth = 0
    for offset in range(0, len(content), 65_536):
        parser.feed(content[offset : offset + 65_536])
        for event, node in cast(
            Iterator[tuple[str, ElementTree.Element]], parser.read_events()
        ):
            if event == "start":
                nodes += 1
                depth += 1
                if (
                    (nodes == 1 and node.tag != expected)
                    or nodes > 100_000
                    or depth > 128
                ):
                    raise ValueError
                if any(
                    "macroenabled" in str(value).casefold()
                    for value in node.attrib.values()
                ):
                    raise ValueError
            else:
                depth -= 1
                node.clear()
    parser.close()
    if nodes == 0 or depth != 0:
        raise ValueError


def validate_attachment_payload(filename: str, payload: bytes) -> tuple[str, str]:
    """Pure bounded type validation; safe to call on unsupported storage platforms."""
    name = normalize_attachment_name(filename)
    if not isinstance(payload, bytes):
        raise IntakeAttachmentError("Attachment content must be bytes.")
    if not 1 <= len(payload) <= MAX_ATTACHMENT_BYTES:
        raise IntakeAttachmentError("Attachment exceeds the 20,000,000-byte limit.")
    suffix = Path(name).suffix.casefold()
    media = MEDIA_TYPES.get(suffix)
    if media is None:
        raise IntakeAttachmentError(
            "Use a PDF, PNG, JPEG, DOCX, EML or TXT attachment."
        )
    if suffix == ".docx":
        _docx(payload)
    elif suffix in {".txt", ".eml"}:
        text = _text(payload)
        if suffix == ".eml":
            headers = re.split(r"\r?\n\r?\n", text, maxsplit=1)[0]
            if len(headers.encode("utf-8")) > 65_536:
                raise IntakeAttachmentError("EML headers exceed the supported limit.")
            try:
                message = BytesHeaderParser(policy=policy.default).parsebytes(payload)
                valid_headers = not message.defects and any(
                    message.get(field)
                    for field in ("From", "To", "Subject", "Date", "Message-ID")
                )
            except Exception:
                # Untrusted standard-library parsing must not disclose payloads.
                raise IntakeAttachmentError("EML headers are invalid.") from None
            if not valid_headers:
                raise IntakeAttachmentError("EML headers are invalid.")
    else:
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
        if not valid:
            raise IntakeAttachmentError("Attachment type does not match its content.")
    return name, media
