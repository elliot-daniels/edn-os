"""Bounded local PDF and DOCX text extraction with structural provenance."""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


class DocumentExtractionError(ValueError):
    """Raised when a document cannot be extracted safely and deterministically."""


@dataclass(frozen=True, slots=True)
class DocumentSection:
    locator: str
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    record_type: str
    transformation_id: str
    sections: tuple[DocumentSection, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(item.text for item in self.sections)


MAX_EXTRACTED_BYTES = 8 * 1024 * 1024
MAX_DOCX_ENTRIES = 2_000
MAX_COMPRESSION_RATIO = 100


def extract_document(path: Path) -> ExtractedDocument:
    extension = path.suffix.casefold()
    if extension == ".docx":
        return _extract_docx(path)
    if extension == ".pdf":
        return _extract_pdf(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise DocumentExtractionError("text document could not be decoded") from error
    return ExtractedDocument(
        "file.text", "local-files.text", (DocumentSection("full-text", text),)
    )


def _extract_docx(path: Path) -> ExtractedDocument:
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                raise DocumentExtractionError("DOCX archive has too many entries")
            if any(item.flag_bits & 1 for item in entries):
                raise DocumentExtractionError("encrypted DOCX is not supported")
            total = sum(item.file_size for item in entries)
            compressed = sum(max(item.compress_size, 1) for item in entries)
            if (
                total > MAX_EXTRACTED_BYTES
                or total > compressed * MAX_COMPRESSION_RATIO
            ):
                raise DocumentExtractionError("DOCX archive exceeds extraction limits")
            try:
                xml = archive.read("word/document.xml")
            except KeyError as error:
                raise DocumentExtractionError(
                    "DOCX main document is missing"
                ) from error
    except (BadZipFile, OSError) as error:
        raise DocumentExtractionError("malformed DOCX container") from error
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise DocumentExtractionError("malformed DOCX XML") from error
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    sections = []
    for index, paragraph in enumerate(root.iter(f"{namespace}p"), start=1):
        text = "".join(
            node.text or "" for node in paragraph.iter(f"{namespace}t")
        ).strip()
        if text:
            sections.append(DocumentSection(f"paragraph:{index}", text))
    if not sections:
        raise DocumentExtractionError("DOCX contains no extractable text")
    return ExtractedDocument("document.docx", "local-files.docx", tuple(sections))


def _extract_pdf(path: Path) -> ExtractedDocument:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise DocumentExtractionError("PDF could not be read") from error
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-1024:]:
        raise DocumentExtractionError("malformed PDF envelope")
    if b"/Encrypt" in payload:
        raise DocumentExtractionError("encrypted PDF is not supported")
    sections = []
    for page, match in enumerate(
        re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", payload, re.DOTALL),
        start=1,
    ):
        stream = match.group(1)
        dictionary = payload[max(0, match.start() - 512) : match.start()]
        if b"/Filter" in dictionary:
            if b"/FlateDecode" not in dictionary:
                raise DocumentExtractionError("unsupported PDF stream filter")
            try:
                stream = zlib.decompress(stream)
            except zlib.error as error:
                raise DocumentExtractionError(
                    "malformed PDF compressed stream"
                ) from error
        text = " ".join(_pdf_strings(stream)).strip()
        if text:
            sections.append(DocumentSection(f"page:{page}", text))
    if not sections:
        raise DocumentExtractionError("PDF contains no safely extractable text")
    if sum(len(item.text.encode("utf-8")) for item in sections) > MAX_EXTRACTED_BYTES:
        raise DocumentExtractionError("PDF extracted text exceeds limits")
    return ExtractedDocument("document.pdf", "local-files.pdf", tuple(sections))


def _pdf_strings(stream: bytes) -> tuple[str, ...]:
    values = []
    for token in re.findall(rb"\((?:\\.|[^\\)])*\)", stream):
        value = token[1:-1]
        value = re.sub(rb"\\([\\()])", rb"\1", value)
        value = value.replace(b"\\n", b"\n").replace(b"\\r", b"\n")
        try:
            decoded = value.decode("utf-8")
        except UnicodeDecodeError:
            decoded = value.decode("latin-1")
        if decoded.strip():
            values.append(decoded.strip())
    return tuple(values)
