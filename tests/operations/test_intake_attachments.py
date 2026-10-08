"""Synthetic supporting-file persistence and containment, never source uploads."""

import base64
import hashlib
import io
import json
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import edn.operations.intake_attachments as module
from edn.operations.intake_attachments import (
    MAX_ATTACHMENT_BYTES,
    IntakeAttachmentError,
    IntakeAttachmentStore,
)

REQUEST = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x02\xff\xd9"


def store(tmp_path):
    root = tmp_path / "runtime-attachments"
    root.mkdir()
    return IntakeAttachmentStore(root)


@pytest.mark.parametrize(
    "name,payload,media",
    [
        ("support.pdf", PDF, "application/pdf"),
        ("photo.PNG", PNG, "image/png"),
        ("photo.jpg", JPEG, "image/jpeg"),
        ("photo.jpeg", JPEG, "image/jpeg"),
    ],
)
def test_originals_roundtrip_restart_and_metadata_has_no_client_paths(
    tmp_path, name, payload, media
):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, name, payload)
    metadata = record.to_dict()
    assert set(metadata) == {
        "attachment_id",
        "request_id",
        "original_name",
        "media_type",
        "size_bytes",
        "sha256",
    }
    assert metadata["media_type"] == media
    assert metadata["size_bytes"] == len(payload)
    assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()
    assert metadata["request_id"] == REQUEST
    reopened = IntakeAttachmentStore(attachments.root)
    assert reopened.get(REQUEST, record.attachment_id) == record
    assert reopened.read(REQUEST, record.attachment_id) == payload
    assert name not in [p.name for p in attachments.root.rglob("*")]


@pytest.mark.parametrize(
    "name",
    [
        "../../outside.pdf",
        "C:\\fakepath\\outside.pdf",
        "\\\\host\\share\\outside.pdf",
        "<tag>outside.pdf",
    ],
)
def test_filename_is_only_normalized_basename_metadata(tmp_path, name):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, name, PDF)
    assert "/" not in record.original_name and "\\" not in record.original_name
    assert "<" not in record.original_name and ":" not in record.original_name
    assert record.original_name.endswith("outside.pdf")
    assert attachments.read(REQUEST, record.attachment_id) == PDF
    assert not (tmp_path / "outside.pdf").exists()


@pytest.mark.parametrize(
    "name,payload",
    [
        ("report.txt", PDF),
        ("report.docx", PDF),
        ("report.pdf", PNG),
        ("photo.png", PDF),
        ("photo.jpg", b"invalid"),
        ("report.pdf", b"%PDF-1.4"),
        ("nul\x00.pdf", PDF),
        ("", PDF),
        ("x" * 161 + ".pdf", PDF),
        ("report.pdf", "text"),
        ("report.pdf", b""),
    ],
)
def test_invalid_uploads_create_no_request_files(tmp_path, name, payload):
    attachments = store(tmp_path)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, name, payload)
    assert list(attachments.root.iterdir()) == []


def test_size_limit_and_stream_reads_are_bounded(tmp_path):
    attachments = store(tmp_path)
    sizes = []

    class Upload(io.BytesIO):
        def read(self, size=-1):
            sizes.append(size)
            return super().read(size)

    with pytest.raises(IntakeAttachmentError, match="size"):
        attachments.attach_stream(
            REQUEST, "support.pdf", Upload(b"x" * (MAX_ATTACHMENT_BYTES + 1))
        )
    assert sizes == [MAX_ATTACHMENT_BYTES + 1]
    exact = b"%PDF-1.4\n" + b"x" * (MAX_ATTACHMENT_BYTES - 16) + b"\n%%EOF\n"
    assert len(exact) == MAX_ATTACHMENT_BYTES
    assert (
        attachments.attach(REQUEST, "exact.pdf", exact).size_bytes
        == MAX_ATTACHMENT_BYTES
    )


@pytest.mark.parametrize(
    "identifier",
    ["../escape", "C:\\escape", "", "not-uuid", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"],
)
def test_invalid_identity_never_becomes_a_path(tmp_path, identifier):
    attachments = store(tmp_path)
    with pytest.raises(IntakeAttachmentError, match="identity"):
        attachments.attach(identifier, "support.pdf", PDF)
    assert list(attachments.root.iterdir()) == []


def test_repeated_storage_id_never_overwrites_original(tmp_path, monkeypatch):
    attachments = store(tmp_path)
    monkeypatch.setattr(module, "uuid4", lambda: UUID(OTHER))
    original = attachments.attach(REQUEST, "support.pdf", PDF)
    with pytest.raises(IntakeAttachmentError, match="stored"):
        attachments.attach(REQUEST, "changed.pdf", PDF + b"changed")
    assert attachments.get(REQUEST, original.attachment_id) == original
    assert attachments.read(REQUEST, original.attachment_id) == PDF


@pytest.mark.parametrize(
    "location", ["root", "ancestor", "request", "attachment", "metadata", "original"]
)
def test_links_and_windows_reparse_points_fail_closed(tmp_path, monkeypatch, location):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, "support.pdf", PDF)
    folder = attachments.root / REQUEST / record.attachment_id
    selected = {
        "root": attachments.root,
        "ancestor": tmp_path,
        "request": attachments.root / REQUEST,
        "attachment": folder,
        "metadata": folder / "metadata.json",
        "original": folder / "original.bin",
    }[location]
    original = Path.lstat

    def linked(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == selected:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return result

    monkeypatch.setattr(Path, "lstat", linked)
    with pytest.raises(IntakeAttachmentError):
        attachments.read(REQUEST, record.attachment_id)
    if location in {"root", "ancestor", "request"}:
        with pytest.raises(IntakeAttachmentError):
            attachments.attach(REQUEST, "second.pdf", PDF)


def test_git_runtime_missing_root_and_filesystem_root_are_rejected(tmp_path):
    with pytest.raises(IntakeAttachmentError):
        IntakeAttachmentStore(tmp_path / "missing")
    with pytest.raises(IntakeAttachmentError):
        IntakeAttachmentStore(Path(tmp_path.anchor))
    (tmp_path / ".git").mkdir()
    with pytest.raises(IntakeAttachmentError, match="Git"):
        IntakeAttachmentStore(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "bytes",
        "oversize",
        "metadata-id",
        "metadata-path",
        "metadata-shape",
        "deep-json",
    ],
)
def test_tampered_original_or_metadata_is_rejected(tmp_path, mutation):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, "support.pdf", PDF)
    folder = attachments.root / REQUEST / record.attachment_id
    metadata = folder / "metadata.json"
    if mutation == "bytes":
        (folder / "original.bin").write_bytes(PDF + b"tampered")
    elif mutation == "oversize":
        (folder / "original.bin").write_bytes(b"x" * (MAX_ATTACHMENT_BYTES + 1))
    elif mutation == "metadata-id":
        metadata.write_text(json.dumps(record.to_dict() | {"request_id": OTHER}))
    elif mutation == "metadata-path":
        metadata.write_text(json.dumps(record.to_dict() | {"path": "private/outside"}))
    elif mutation == "deep-json":
        metadata.write_text("[" * 1500 + "0" + "]" * 1500)
    else:
        metadata.write_text("[]")
    with pytest.raises(IntakeAttachmentError):
        attachments.read(REQUEST, record.attachment_id)
    with pytest.raises(IntakeAttachmentError):
        attachments.get(OTHER, record.attachment_id)


@pytest.mark.parametrize("failure", ["fsync", "publish"])
def test_failed_publication_never_returns_completed_attachment(
    tmp_path, monkeypatch, failure
):
    attachments = store(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("PRIVATE_RUNTIME_PATH")

    operation = "rename" if module.os.name == "nt" else "link"
    monkeypatch.setattr(module.os, operation if failure == "publish" else failure, fail)
    with pytest.raises(IntakeAttachmentError) as error:
        attachments.attach(REQUEST, "support.pdf", PDF)
    assert str(error.value) == "Attachment could not be stored."
    assert list(attachments.root.rglob("metadata.json")) == []


def test_record_mutation_type_validation(tmp_path):
    record = store(tmp_path).attach(REQUEST, "support.pdf", PDF)
    for changes in (
        {"size_bytes": True},
        {"size_bytes": 0},
        {"sha256": "invalid"},
        {"original_name": "../support.pdf"},
        {"media_type": "text/html"},
    ):
        with pytest.raises(IntakeAttachmentError):
            replace(record, **changes)


def test_metadata_publication_never_replaces_a_preexisting_marker(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)
    original = Path.mkdir
    sentinel = b"existing metadata"

    def insert_marker(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path.parent.name == REQUEST:
            (path / "metadata.json").write_bytes(sentinel)

    monkeypatch.setattr(Path, "mkdir", insert_marker)
    with pytest.raises(IntakeAttachmentError, match="stored"):
        attachments.attach(REQUEST, "support.pdf", PDF)
    assert [p.read_bytes() for p in attachments.root.rglob("metadata.json")] == [
        sentinel
    ]


def test_permission_errors_are_fixed_without_runtime_path_disclosure(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)
    original = Path.lstat

    def denied(path, *args, **kwargs):
        if path == attachments.root:
            raise PermissionError("PRIVATE_PATH_CONTENT")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(IntakeAttachmentError) as error:
        attachments.attach(REQUEST, "support.pdf", PDF)
    assert str(error.value) == "Attachment storage is unavailable."
