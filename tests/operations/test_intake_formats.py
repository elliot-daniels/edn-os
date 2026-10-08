"""Pure evidence-format boundaries shared by uploads and backend approval."""

import base64
import io
import stat

import pytest

import edn.operations.intake_formats as module
from edn.operations.intake_formats import (
    MAX_ATTACHMENT_BYTES,
    IntakeAttachmentError,
    validate_attachment_payload,
)

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x02\xff\xd9"


def docx_bytes(extra=()):
    from zipfile import ZipFile, ZipInfo

    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "word/document.xml",
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>',
        )
        for name, value in extra:
            info = ZipInfo(name)
            info.filename = info.orig_filename = name
            archive.writestr(info, value)
    return stream.getvalue()


@pytest.mark.parametrize(
    "name,payload,media",
    [
        ("support.pdf", PDF, "application/pdf"),
        ("photo.png", PNG, "image/png"),
        ("photo.jpeg", JPEG, "image/jpeg"),
        ("notes.txt", "Synthetic supporting text ✓".encode(), "text/plain"),
        (
            "mail.eml",
            b"Subject: Synthetic example\r\nFrom: synthetic@example.invalid\r\n"
            b"\r\nSupporting text\r\n",
            "message/rfc822",
        ),
        (
            "report.docx",
            docx_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_pure_supported_format_validation_runs_without_storage(name, payload, media):
    assert validate_attachment_payload(name, payload) == (name, media)


@pytest.mark.parametrize(
    "name,payload",
    [
        ("notes.txt", b"invalid\xff"),
        ("notes.txt", b"nul\x00"),
        ("mail.eml", b"no message headers"),
        ("mail.eml", b"Subject: Example\n\n\xff"),
        ("report.docx", PDF),
        ("report.docx", docx_bytes((("../escape", b"invalid"),))),
        ("report.docx", docx_bytes((("C:drive", b"invalid"),))),
        ("report.docx", docx_bytes((("nested\\escape", b"invalid"),))),
        ("report.docx", docx_bytes((("word/vbaProject.bin", b"macro"),))),
    ],
)
def test_pure_text_and_docx_reject_unsafe_payloads(name, payload):
    with pytest.raises(IntakeAttachmentError):
        validate_attachment_payload(name, payload)


@pytest.mark.parametrize(
    "kind",
    [
        "symlink",
        "encrypted",
        "expanded",
        "members",
        "ratio",
        "doctype",
        "depth",
        "macro-type",
    ],
)
def test_docx_container_and_xml_bounds_are_enforced_without_storage(kind):
    import struct
    from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

    stream = io.BytesIO()
    compression = ZIP_DEFLATED if kind in {"ratio", "expanded"} else ZIP_STORED
    with ZipFile(stream, "w", compression=compression) as archive:
        content_types = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
        if kind == "macro-type":
            content_types = (
                b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                b'<Override ContentType="MacroEnabled"/></Types>'
            )
        archive.writestr("[Content_Types].xml", content_types)
        document = b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'
        if kind == "doctype":
            document = b'<!DOCTYPE x [<!ENTITY data "boom">]>' + document
        if kind == "depth":
            document = (
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                + b"<w:x>" * 129
                + b"</w:x>" * 129
                + b"</w:document>"
            )
        archive.writestr("word/document.xml", document)
        if kind == "symlink":
            link = ZipInfo("word/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, b"../outside")
        elif kind == "members":
            for index in range(module.MAX_DOCX_ENTRIES):
                archive.writestr(f"word/item-{index}", b"")
        elif kind == "expanded":
            archive.writestr("word/big", b"x" * MAX_ATTACHMENT_BYTES)
        elif kind == "ratio":
            archive.writestr("word/compressed", b"x" * 1_000_000)
    payload = stream.getvalue()
    if kind == "encrypted":
        encrypted = bytearray(payload)
        offset = encrypted.index(b"PK\x01\x02")
        struct.pack_into("<H", encrypted, offset + 8, 1)
        payload = bytes(encrypted)
    with pytest.raises(IntakeAttachmentError):
        validate_attachment_payload("report.docx", payload)


def test_encoded_docx_dtd_cannot_bypass_xml_guard():
    from zipfile import ZipFile

    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        xml = '<!DOCTYPE x [<!ENTITY payload "boom">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        archive.writestr("word/document.xml", xml.encode("utf-16"))
    with pytest.raises(IntakeAttachmentError, match="DOCX"):
        validate_attachment_payload("report.docx", stream.getvalue())


def test_eml_parser_failures_are_source_free(monkeypatch):
    def broken(*args, **kwargs):
        raise RecursionError("PRIVATE_SOURCE_CONTENT")

    monkeypatch.setattr(module.BytesHeaderParser, "parsebytes", broken)
    with pytest.raises(IntakeAttachmentError) as error:
        validate_attachment_payload("mail.eml", b"Subject: Example\n\nSynthetic body")
    assert str(error.value) == "EML headers are invalid."


def test_decimal_upload_bounds_are_exact_and_create_no_storage(monkeypatch):
    from pathlib import Path

    for operation in ("mkdir", "chmod", "open", "lstat", "exists", "resolve", "is_dir"):
        monkeypatch.setattr(
            Path,
            operation,
            lambda *a, **k: pytest.fail("Pure codec touched filesystem"),
        )
    payload = b"%PDF-1.4\n" + b"x" * (MAX_ATTACHMENT_BYTES - 16) + b"\n%%EOF\n"
    assert len(payload) == 20_000_000
    assert validate_attachment_payload("support.pdf", payload) == (
        "support.pdf",
        "application/pdf",
    )
    with pytest.raises(IntakeAttachmentError, match="20,000,000"):
        validate_attachment_payload("support.pdf", payload + b"x")
    assert module.MAX_REQUEST_BYTES == 100_000_000
    assert module.MAX_REQUEST_FILES == 100
