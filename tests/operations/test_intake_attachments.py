"""Synthetic supporting-file persistence and containment, never source uploads."""

import base64
import hashlib
import io
import json
import os
import stat
import sys
from dataclasses import replace
from functools import wraps
from pathlib import Path
from uuid import UUID

import pytest

import edn.operations.intake_attachments as module
from edn.operations.intake_attachments import (
    MAX_ATTACHMENT_BYTES,
    MAX_METADATA_BYTES,
    MAX_REQUEST_BYTES,
    IntakeAttachmentError,
    IntakeAttachmentStore,
)
from edn.operations.intake_security import IntakeSecurityError

REQUEST = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x02\xff\xd9"


def linux_storage_test(function):
    @wraps(function)
    def run(*args, **kwargs):
        if os.name != "posix" or sys.platform != "linux":
            root = kwargs["tmp_path"] / "refused-storage"
            with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
                IntakeAttachmentStore(root)
            assert not root.exists()
            return
        return function(*args, **kwargs)

    return run


def store(tmp_path):
    root = tmp_path / "runtime-attachments"
    root.mkdir(mode=0o700)
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
@linux_storage_test
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
@linux_storage_test
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
        ("report.txt", b"\xff"),
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
@linux_storage_test
def test_invalid_uploads_create_no_request_files(tmp_path, name, payload):
    attachments = store(tmp_path)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, name, payload)
    assert list(attachments.root.iterdir()) == []


@linux_storage_test
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
@linux_storage_test
def test_invalid_identity_never_becomes_a_path(tmp_path, identifier):
    attachments = store(tmp_path)
    with pytest.raises(IntakeAttachmentError, match="identity"):
        attachments.attach(identifier, "support.pdf", PDF)
    assert list(attachments.root.iterdir()) == []


@linux_storage_test
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
@linux_storage_test
def test_existing_real_symlinks_fail_closed(tmp_path, location):
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
    moved = selected.with_name(selected.name + "-authorized-old")
    is_directory = selected.is_dir()
    selected.rename(moved)
    selected.symlink_to(moved, target_is_directory=is_directory)
    with pytest.raises((IntakeAttachmentError, IntakeSecurityError)):
        attachments.read(REQUEST, record.attachment_id)
    if location in {"root", "ancestor", "request"}:
        with pytest.raises((IntakeAttachmentError, IntakeSecurityError)):
            attachments.attach(REQUEST, "second.pdf", PDF)


@linux_storage_test
def test_git_runtime_missing_root_and_filesystem_root_are_rejected(tmp_path):
    with pytest.raises(IntakeAttachmentError):
        IntakeAttachmentStore(tmp_path / "missing")
    with pytest.raises((IntakeAttachmentError, IntakeSecurityError)):
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
@linux_storage_test
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
@linux_storage_test
def test_failed_publication_never_returns_completed_attachment(
    tmp_path, monkeypatch, failure
):
    attachments = store(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("PRIVATE_RUNTIME_PATH")

    operation = "replace"
    monkeypatch.setattr(module.os, operation if failure == "publish" else failure, fail)
    with pytest.raises(IntakeAttachmentError) as error:
        attachments.attach(REQUEST, "support.pdf", PDF)
    assert str(error.value) == "Attachment could not be stored."
    assert list(attachments.root.rglob("metadata.json")) == []


@linux_storage_test
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


@linux_storage_test
def test_metadata_publication_never_replaces_a_preexisting_marker(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)
    original = module.AnchoredDirectory.publish
    sentinel = b"existing metadata"

    def insert_marker(directory, source, target):
        if target == "metadata.json":
            descriptor = directory.open_file(target, create=True, write=True)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(sentinel)
        return original(directory, source, target)

    monkeypatch.setattr(module.AnchoredDirectory, "publish", insert_marker)
    with pytest.raises(IntakeAttachmentError, match="stored"):
        attachments.attach(REQUEST, "support.pdf", PDF)
    assert [p.read_bytes() for p in attachments.root.rglob("metadata.json")] == [
        sentinel
    ]


@linux_storage_test
def test_permission_errors_are_fixed_without_runtime_path_disclosure(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)

    def denied(*args, **kwargs):
        raise PermissionError("PRIVATE_PATH_CONTENT")

    monkeypatch.setattr(module.AnchoredDirectory, "__init__", denied)
    with pytest.raises(IntakeAttachmentError) as error:
        attachments.attach(REQUEST, "support.pdf", PDF)
    assert str(error.value) == "Attachment could not be stored."


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


def test_native_windows_constructor_refuses_before_filesystem_calls(monkeypatch):
    if os.name == "posix" and sys.platform == "linux":
        # Force only the platform guard, without changing global os.name or Paths.
        def unsupported():
            raise IntakeSecurityError("Protected intake storage requires Linux or WSL")

        monkeypatch.setattr(module, "require_supported_platform", unsupported)
    for operation in ("mkdir", "chmod", "open", "lstat", "exists", "resolve", "is_dir"):
        monkeypatch.setattr(
            Path,
            operation,
            lambda *a, **k: pytest.fail("Filesystem access before platform refusal"),
        )
    with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
        IntakeAttachmentStore(Path("/never-created-intake-storage"))


@linux_storage_test
def test_linux_private_modes_and_hardlinks_are_rejected(tmp_path):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, "notes.txt", b"synthetic text")
    folder = attachments.root / REQUEST / record.attachment_id
    for directory in (attachments.root, folder.parent, folder):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert directory.stat().st_uid == os.geteuid()
    for path in attachments.root.rglob("*"):
        if path.is_file():
            info = path.stat()
            assert stat.S_IMODE(info.st_mode) == 0o600
            assert info.st_uid == os.geteuid() and info.st_nlink == 1
    os.link(folder / "original.bin", tmp_path / "hardlinked-original")
    with pytest.raises((IntakeSecurityError, IntakeAttachmentError)):
        attachments.read(REQUEST, record.attachment_id)


@linux_storage_test
def test_linux_unsafe_file_mode_and_owner_are_rejected(tmp_path, monkeypatch):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, "notes.txt", b"synthetic text")
    original = attachments.root / REQUEST / record.attachment_id / "original.bin"
    original.chmod(0o644)
    with pytest.raises((IntakeSecurityError, IntakeAttachmentError)):
        attachments.read(REQUEST, record.attachment_id)
    original.chmod(0o600)
    import edn.operations.intake_security as security

    monkeypatch.setattr(security.os, "geteuid", lambda: original.stat().st_uid + 1)
    with pytest.raises((IntakeSecurityError, IntakeAttachmentError)):
        attachments.get(REQUEST, record.attachment_id)


_BARRIER = None


def _init_upload_worker(barrier):
    global _BARRIER
    _BARRIER = barrier


def _concurrent_upload(root):
    attachments = IntakeAttachmentStore(Path(root))
    _BARRIER.wait(timeout=30)
    marker = str(os.getpid()).encode()
    payload = b"%PDF-1.4\n" + b"x" * (MAX_ATTACHMENT_BYTES - 16) + b"\n%%EOF\n"
    payload = payload[:20] + marker + payload[20 + len(marker) :]
    try:
        attachments.attach(REQUEST, "concurrent.pdf", payload)
        return "stored"
    except IntakeAttachmentError:
        return "refused"


@linux_storage_test
def test_aggregate_quota_is_atomic_across_competing_processes(tmp_path):
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    attachments = store(tmp_path)
    payload = b"%PDF-1.4\n" + b"x" * (MAX_ATTACHMENT_BYTES - 16) + b"\n%%EOF\n"
    for index in range(4):
        distinct = payload[:20] + str(index).encode() + payload[21:]
        attachments.attach(REQUEST, "support.pdf", distinct)
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=2,
        mp_context=context,
        initializer=_init_upload_worker,
        initargs=(context.Barrier(2),),
    ) as pool:
        results = list(pool.map(_concurrent_upload, [str(attachments.root)] * 2))
    assert sorted(results) == ["refused", "stored"]
    originals = list((attachments.root / REQUEST).rglob("original.bin"))
    assert len(originals) == 5
    assert sum(path.stat().st_size for path in originals) == MAX_REQUEST_BYTES
    ledger = json.loads((attachments.root / REQUEST / "attachments.json").read_text())
    assert len(ledger["entries"]) == 5
    assert all(entry["state"] == "complete" for entry in ledger["entries"])
    assert sum(entry["size_bytes"] for entry in ledger["entries"]) == MAX_REQUEST_BYTES


@linux_storage_test
def test_failed_original_write_preserves_conservative_reservation(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)
    original = module._publish_file

    def interrupted(directory, name, payload):
        if name == "original.bin":
            raise OSError("PRIVATE_SOURCE_CONTENT")
        return original(directory, name, payload)

    monkeypatch.setattr(module, "_publish_file", interrupted)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, "notes.txt", b"synthetic text")
    ledger = json.loads((attachments.root / REQUEST / "attachments.json").read_text())
    assert ledger["entries"][0]["state"] == "reserved"
    assert ledger["entries"][0]["size_bytes"] == len(b"synthetic text")
    with pytest.raises(IntakeAttachmentError):
        attachments.get(REQUEST, ledger["entries"][0]["attachment_id"])
    monkeypatch.setattr(module, "_publish_file", original)
    record = attachments.attach(REQUEST, "notes.txt", b"second file")
    assert attachments.read(REQUEST, record.attachment_id) == b"second file"


@linux_storage_test
def test_tampered_quota_or_untracked_physical_files_fail_closed(tmp_path):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, "notes.txt", b"synthetic text")
    ledger_path = attachments.root / REQUEST / "attachments.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["entries"][0]["size_bytes"] = 1
    ledger_path.write_text(json.dumps(ledger))
    with pytest.raises(IntakeAttachmentError):
        attachments.get(REQUEST, record.attachment_id)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, "second.txt", b"synthetic text")


@pytest.mark.parametrize("operation", ["attach", "get", "read", "stream"])
def test_windows_storage_methods_refuse_before_io_even_without_constructor(
    monkeypatch, operation
):
    if os.name == "posix" and sys.platform == "linux":

        def unsupported():
            raise IntakeSecurityError("Protected intake storage requires Linux or WSL")

        monkeypatch.setattr(module, "require_supported_platform", unsupported)
    attachments = object.__new__(IntakeAttachmentStore)
    attachments.root = Path("/never-created-intake-storage")
    for method in ("mkdir", "chmod", "open", "lstat", "exists", "resolve", "is_dir"):
        monkeypatch.setattr(
            Path,
            method,
            lambda *a, **k: pytest.fail("Filesystem access before refusal"),
        )

    class Upload(io.BytesIO):
        def read(self, *args, **kwargs):
            pytest.fail("Upload read before unsupported-platform refusal")

    actions = {
        "attach": lambda: attachments.attach(REQUEST, "notes.txt", b"synthetic text"),
        "get": lambda: attachments.get(REQUEST, OTHER),
        "read": lambda: attachments.read(REQUEST, OTHER),
        "stream": lambda: attachments.attach_stream(REQUEST, "notes.txt", Upload()),
    }
    with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
        actions[operation]()


@linux_storage_test
@pytest.mark.parametrize(
    "name,payload",
    [
        ("notes.txt", b"synthetic text"),
        (
            "mail.eml",
            b"From: synthetic@example.invalid\r\nSubject: Example\r\n\r\nBody",
        ),
        ("report.docx", docx_bytes()),
    ],
)
def test_added_formats_persist_original_bytes_without_extraction(
    tmp_path, name, payload
):
    attachments = store(tmp_path)
    record = attachments.attach(REQUEST, name, payload)
    assert (
        IntakeAttachmentStore(attachments.root).read(REQUEST, record.attachment_id)
        == payload
    )


@linux_storage_test
def test_untracked_original_folder_cannot_bypass_physical_quota(tmp_path):
    attachments = store(tmp_path)
    attachments.attach(REQUEST, "notes.txt", b"synthetic text")
    orphan = attachments.root / REQUEST / OTHER
    orphan.mkdir(mode=0o700)
    descriptor = os.open(
        orphan / "original.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"untracked synthetic bytes")
    second = attachments.attach(REQUEST, "notes.txt", b"second file")
    assert attachments.read(REQUEST, second.attachment_id) == b"second file"
    assert not orphan.exists()
    assert list((attachments.root / ".quarantine" / REQUEST).rglob("original.bin"))
    ledger = json.loads((attachments.root / REQUEST / "attachments.json").read_text())
    assert len(ledger["entries"]) == 2


@linux_storage_test
def test_per_request_file_count_is_bounded_at_one_hundred(tmp_path):
    attachments = store(tmp_path)
    for index in range(module.MAX_REQUEST_FILES):
        attachments.attach(
            REQUEST, "notes.txt", f"small synthetic text {index}".encode()
        )
    with pytest.raises(IntakeAttachmentError, match="100 files"):
        attachments.attach(REQUEST, "notes.txt", b"extra file")
    ledger = json.loads((attachments.root / REQUEST / "attachments.json").read_text())
    assert len(ledger["entries"]) == 100
    assert (
        attachments.root / REQUEST / "attachments.json"
    ).stat().st_size < MAX_METADATA_BYTES


@linux_storage_test
@pytest.mark.parametrize("boundary", ["root", "request", "attachment"])
def test_validated_parent_swap_never_writes_outside_root(
    tmp_path, monkeypatch, boundary
):
    attachments = store(tmp_path)
    outside = tmp_path / "outside-unapproved"
    outside.mkdir(mode=0o700)
    marker = outside / "sentinel"
    marker.write_bytes(b"unchanged outside")
    original_child = module.AnchoredDirectory.child
    swapped = []
    old_authorized = []

    def swap_after_open(directory, name, **kwargs):
        opened = original_child(directory, name, **kwargs)
        if kwargs.get("create") and not swapped:
            if boundary == "root" and name == REQUEST:
                selected = attachments.root
            elif boundary == "request" and name != REQUEST:
                selected = attachments.root / REQUEST
            elif boundary == "attachment" and name != REQUEST:
                selected = attachments.root / REQUEST / name
            else:
                return opened
            moved = selected.with_name(selected.name + "-authorized-old")
            selected.rename(moved)
            selected.symlink_to(outside, target_is_directory=True)
            old_authorized.append(moved)
            swapped.append(True)
        return opened

    monkeypatch.setattr(module.AnchoredDirectory, "child", swap_after_open)
    record = attachments.attach(REQUEST, "support.pdf", PDF)
    assert swapped
    assert list(outside.iterdir()) == [marker]
    assert marker.read_bytes() == b"unchanged outside"
    assert not list(outside.rglob("original.bin"))
    if boundary == "root":
        assert (
            IntakeAttachmentStore(old_authorized[0]).read(REQUEST, record.attachment_id)
            == PDF
        )
    else:
        assert (
            old_authorized[0]
            / (record.attachment_id if boundary == "request" else "")
            / "original.bin"
        ).read_bytes() == PDF


@linux_storage_test
@pytest.mark.parametrize("failure", ["disk_error", "hard_exit"])
@pytest.mark.parametrize("stage", ["original", "metadata"])
def test_interrupted_staging_never_publishes_partial_final_names(
    tmp_path, monkeypatch, failure, stage
):
    attachments = store(tmp_path)
    if failure == "disk_error":
        original_stage = module._stage_file

        def partial_stage(directory, name, payload):
            if name.startswith(".pending-") and payload.startswith(
                b"%PDF-" if stage == "original" else b"{"
            ):
                descriptor = directory.open_file(name, create=True, write=True)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload[:3])
                    stream.flush()
                raise OSError("PRIVATE_DISK_FAILURE")
            return original_stage(directory, name, payload)

        monkeypatch.setattr(module, "_stage_file", partial_stage)
        with pytest.raises(IntakeAttachmentError):
            attachments.attach(REQUEST, "support.pdf", PDF)
    else:
        import subprocess

        code = """
import os, sys
from pathlib import Path
import edn.operations.intake_attachments as module
from edn.operations.intake_attachments import IntakeAttachmentStore
original = module._stage_file
def partial_stage(directory, name, payload):
    if (name.startswith('.pending-') and
        payload.startswith(b'%PDF-' if sys.argv[3] == 'original' else b'{')):
        descriptor = directory.open_file(name, create=True, write=True)
        os.write(descriptor, payload[:3])
        os.fsync(descriptor)
        os._exit(77)
    return original(directory, name, payload)
module._stage_file = partial_stage
IntakeAttachmentStore(Path(sys.argv[1])).attach(
    sys.argv[2], 'support.pdf', b'%PDF-1.4\\n%%EOF\\n'
)
"""
        root = Path(__file__).resolve().parents[2]
        environment = dict(
            os.environ, PYTHONPATH=os.pathsep.join((str(root / "src"), str(root)))
        )
        result = subprocess.run(
            [sys.executable, "-c", code, str(attachments.root), REQUEST, stage],
            env=environment,
            cwd=root,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 77, result.stderr.decode()
    ledger = json.loads((attachments.root / REQUEST / "attachments.json").read_text())
    record_id = ledger["entries"][0]["attachment_id"]
    assert ledger["entries"][0]["state"] == "reserved"
    folder = attachments.root / REQUEST / record_id
    if stage == "original":
        assert not (folder / "original.bin").exists()
    else:
        assert (folder / "original.bin").read_bytes().startswith(b"%PDF-")
    assert not (folder / "metadata.json").exists()
    with pytest.raises(IntakeAttachmentError):
        IntakeAttachmentStore(attachments.root).read(REQUEST, record_id)


@linux_storage_test
def test_same_request_sha256_replay_keeps_metadata_and_quota(tmp_path):
    attachments = store(tmp_path)
    first = attachments.attach(REQUEST, "same.pdf", PDF)
    before = (attachments.root / REQUEST / "attachments.json").read_bytes()
    assert attachments.attach(REQUEST, "renamed.pdf", PDF) == first
    assert (
        IntakeAttachmentStore(attachments.root).attach(REQUEST, "same.pdf", PDF)
        == first
    )
    assert (attachments.root / REQUEST / "attachments.json").read_bytes() == before
    assert len(list((attachments.root / REQUEST).rglob("original.bin"))) == 1
    other = attachments.attach(OTHER, "same.pdf", PDF)
    assert other.attachment_id != first.attachment_id


@linux_storage_test
def test_metadata_publish_failure_quarantines_on_restart_and_releases_committed_quota(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)
    publish = module._publish_file

    def fail_metadata(directory, name, payload):
        if name == "metadata.json":
            raise OSError("PRIVATE_FAILURE")
        return publish(directory, name, payload)

    monkeypatch.setattr(module, "_publish_file", fail_metadata)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, "support.pdf", PDF)
    ledger = attachments.root / REQUEST / "attachments.json"
    failed = json.loads(ledger.read_text())["entries"][0]
    assert failed["state"] == "reserved"
    monkeypatch.setattr(module, "_publish_file", publish)
    reopened = IntakeAttachmentStore(attachments.root)
    assert json.loads(ledger.read_text())["entries"] == []
    assert not (attachments.root / REQUEST / failed["attachment_id"]).exists()
    retained = list((attachments.root / ".quarantine" / REQUEST).rglob("original.bin"))
    assert len(retained) == 1 and retained[0].read_bytes() == PDF
    assert list((attachments.root / ".quarantine" / REQUEST).rglob("sweep.json"))
    successful = reopened.attach(REQUEST, "support.pdf", PDF)
    assert reopened.read(REQUEST, successful.attachment_id) == PDF


@pytest.mark.parametrize("interruptions", [1, 3])
@linux_storage_test
def test_interrupted_recovery_finishes_cleanup_on_first_reopen(
    tmp_path, monkeypatch, interruptions
):
    import subprocess

    attachments = store(tmp_path)
    good = attachments.attach(REQUEST, "complete.pdf", PDF)
    incomplete = PDF.replace(b"1 0 obj", b"2 0 obj")
    ledger = attachments.root / REQUEST / "attachments.json"
    complete_entries = json.loads(ledger.read_text())["entries"]
    publish = module._publish_file

    def fail_metadata(directory, name, payload):
        if name == "metadata.json":
            raise OSError("synthetic metadata failure")
        return publish(directory, name, payload)

    monkeypatch.setattr(module, "_publish_file", fail_metadata)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, "incomplete.pdf", incomplete)
    monkeypatch.setattr(module, "_publish_file", publish)
    code = """
import os, sys
from pathlib import Path
from edn.operations.intake_attachments import IntakeAttachmentStore
from edn.operations.intake_security import AnchoredDirectory
original = AnchoredDirectory.replace
def interrupted(directory, source, target):
    if target == 'attachments.json' and directory.exists('.recovery.json'):
        assert source.startswith('.quota-') and directory.exists(source)
        os._exit(77)
    return original(directory, source, target)
AnchoredDirectory.replace = interrupted
IntakeAttachmentStore(Path(sys.argv[1]))
"""
    repo = Path(__file__).resolve().parents[2]
    environment = dict(
        os.environ, PYTHONPATH=os.pathsep.join((str(repo / "src"), str(repo)))
    )
    for _ in range(interruptions):
        result = subprocess.run(
            [sys.executable, "-c", code, str(attachments.root)],
            cwd=repo,
            env=environment,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 77, result.stderr.decode()
    assert len(list((attachments.root / REQUEST).glob(".quota-*"))) == interruptions
    reopened = IntakeAttachmentStore(attachments.root)
    assert reopened.get(REQUEST, good.attachment_id) == good
    assert reopened.read(REQUEST, good.attachment_id) == PDF
    assert not list((attachments.root / REQUEST).glob(".quota-*"))
    assert not (attachments.root / REQUEST / ".recovery.json").exists()
    assert json.loads(ledger.read_text())["entries"] == complete_entries
    originals = list((attachments.root / ".quarantine").rglob("original.bin"))
    assert len(originals) == 1 and originals[0].read_bytes() == incomplete
    snapshot = {
        str(path.relative_to(attachments.root)): path.read_bytes()
        for path in attachments.root.rglob("*")
        if path.is_file()
    }
    IntakeAttachmentStore(attachments.root)
    assert snapshot == {
        str(path.relative_to(attachments.root)): path.read_bytes()
        for path in attachments.root.rglob("*")
        if path.is_file()
    }


@linux_storage_test
def test_recovery_failure_never_frees_quota_before_committed_sweep(
    tmp_path, monkeypatch
):
    attachments = store(tmp_path)
    publish = module._publish_file

    def fail_metadata(directory, name, payload):
        if name == "metadata.json":
            raise OSError("synthetic failure")
        return publish(directory, name, payload)

    monkeypatch.setattr(module, "_publish_file", fail_metadata)
    with pytest.raises(IntakeAttachmentError):
        attachments.attach(REQUEST, "support.pdf", PDF)
    monkeypatch.setattr(module, "_publish_file", publish)
    ledger = attachments.root / REQUEST / "attachments.json"
    before = ledger.read_bytes()
    save = module.IntakeAttachmentStore._save_quota

    def fail_commit(*args, **kwargs):
        raise OSError("synthetic sweep failure")

    monkeypatch.setattr(module.IntakeAttachmentStore, "_save_quota", fail_commit)
    with pytest.raises(IntakeAttachmentError, match="recovery"):
        IntakeAttachmentStore(attachments.root)
    assert ledger.read_bytes() == before
    assert (attachments.root / REQUEST / ".recovery.json").exists()
    monkeypatch.setattr(module.IntakeAttachmentStore, "_save_quota", save)
    IntakeAttachmentStore(attachments.root)
    assert json.loads(ledger.read_text())["entries"] == []
    assert not (attachments.root / REQUEST / ".recovery.json").exists()
    assert (
        len(list((attachments.root / ".quarantine" / REQUEST).rglob("original.bin")))
        == 1
    )


@linux_storage_test
def test_stale_pending_quota_and_orphan_folder_are_quarantined_without_deletion(
    tmp_path,
):
    attachments = store(tmp_path)
    good = attachments.attach(REQUEST, "support.pdf", PDF)
    request_path = attachments.root / REQUEST
    pending = request_path / (".quota-" + OTHER)
    descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"partial private receipt")
    orphan = request_path / OTHER
    orphan.mkdir(mode=0o700)
    descriptor = os.open(
        orphan / (".pending-" + OTHER), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"partial private original")
    reopened = IntakeAttachmentStore(attachments.root)
    assert reopened.read(REQUEST, good.attachment_id) == PDF
    assert not pending.exists() and not orphan.exists()
    quarantine = attachments.root / ".quarantine" / REQUEST
    retained = [
        p.read_bytes()
        for p in quarantine.rglob("*")
        if p.is_file() and p.name != "sweep.json"
    ]
    assert b"partial private receipt" in retained
    assert b"partial private original" in retained
