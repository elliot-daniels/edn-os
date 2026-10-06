"""Synthetic hostile-manifest and isolated restore security regression tests."""

import json
from pathlib import Path

import pytest

from edn.intelligence.backup import BackupComponent, OperationalBackup


def _backup(tmp_path: Path) -> Path:
    source = tmp_path / "state.bin"
    source.write_bytes(b"synthetic operational state")
    root = tmp_path / "backup"
    OperationalBackup().create(root, components=(BackupComponent("state", source),))
    return root


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.bin",
        "..\\outside.bin",
        "/outside.bin",
        "C:\\outside.bin",
        "C:outside.bin",
        "\\\\host\\share\\outside.bin",
        "000-state.bin:stream",
        "manifest.json",
        "nested/000-state.bin",
    ],
)
def test_restore_rejects_unsafe_manifest_filename_before_writing(
    tmp_path: Path, filename: str
) -> None:
    root = _backup(tmp_path)
    manifest = root / "manifest.json"
    value = json.loads(manifest.read_text())
    value["components"][0]["filename"] = filename
    manifest.write_text(json.dumps(value))
    destination = tmp_path / "restored"
    with pytest.raises(ValueError):
        OperationalBackup().restore(root, destination)
    assert not destination.exists()
    assert (tmp_path / "state.bin").read_bytes() == b"synthetic operational state"


@pytest.mark.parametrize(
    "name", ["../../outside", "state/other", "state\\other", "C:state", ".", ""]
)
def test_create_rejects_unsafe_names_before_writing(tmp_path: Path, name: str) -> None:
    source = tmp_path / "state.bin"
    source.write_bytes(b"synthetic")
    destination = tmp_path / "backup"
    with pytest.raises(ValueError):
        OperationalBackup().create(
            destination, components=(BackupComponent(name, source),)
        )
    assert not destination.exists()


@pytest.mark.parametrize(
    "field,value",
    [("name", "authentication_tokens"), ("size_bytes", -1), ("sha256", "invalid")],
)
def test_restore_rejects_invalid_component_metadata(
    tmp_path: Path, field: str, value: object
) -> None:
    root = _backup(tmp_path)
    manifest = root / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["components"][0][field] = value
    manifest.write_text(json.dumps(payload))
    with pytest.raises((ValueError, PermissionError)):
        OperationalBackup().restore(root, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_restore_rejects_duplicate_components(tmp_path: Path) -> None:
    root = _backup(tmp_path)
    manifest = root / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["components"].append(payload["components"][0])
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unique"):
        OperationalBackup().restore(root, tmp_path / "restored")


@pytest.mark.parametrize(
    "location", ["source", "manifest", "component", "destination", "ancestor"]
)
def test_links_fail_closed_before_restore_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    root = _backup(tmp_path)
    destination = tmp_path / "restored"
    linked = {
        "source": root,
        "manifest": root / "manifest.json",
        "component": root / "000-state.bin",
        "destination": destination,
        "ancestor": tmp_path,
    }[location]
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == linked or original(path)
    )
    with pytest.raises(ValueError, match="symlinks"):
        OperationalBackup().restore(root, destination)
    assert not destination.exists()


def test_restore_never_overwrites_existing_target(tmp_path: Path) -> None:
    root = _backup(tmp_path)
    destination = tmp_path / "restored"
    destination.mkdir()
    marker = destination / "000-state.bin"
    marker.write_bytes(b"existing state")
    with pytest.raises(FileExistsError):
        OperationalBackup().restore(root, destination)
    assert marker.read_bytes() == b"existing state"


def test_symlinked_component_cannot_escape_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _backup(tmp_path)
    component = root / "000-state.bin"
    outside = tmp_path / "outside.bin"
    outside.write_bytes(component.read_bytes())
    component.unlink()
    try:
        component.symlink_to(outside)
    except OSError as error:
        if error.winerror == 1314:
            # Linux exercises a real symlink; Windows without symlink privilege
            # still exercises the identical fail-closed predicate.
            original = Path.is_symlink
            monkeypatch.setattr(
                Path, "is_symlink", lambda path: path == component or original(path)
            )
        else:
            raise
    with pytest.raises(ValueError, match="symlinks"):
        OperationalBackup().restore(root, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    assert outside.read_bytes() == b"synthetic operational state"


def test_restore_detects_source_change_after_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _backup(tmp_path)
    service = OperationalBackup()
    original = service.verify

    def changed(backup: Path):
        manifest = original(backup)
        (root / "000-state.bin").write_bytes(b"changed after verification")
        return manifest

    monkeypatch.setattr(service, "verify", changed)
    destination = tmp_path / "restored"
    with pytest.raises(ValueError, match="during restore"):
        service.restore(root, destination)
    assert not (destination / "manifest.json").exists()


def test_restore_exclusive_write_refuses_file_created_after_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _backup(tmp_path)
    destination = tmp_path / "restored"
    original = Path.mkdir

    def inserted(path: Path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == destination:
            (path / "000-state.bin").write_bytes(b"existing state")

    monkeypatch.setattr(Path, "mkdir", inserted)
    with pytest.raises(FileExistsError):
        OperationalBackup().restore(root, destination)
    assert (destination / "000-state.bin").read_bytes() == b"existing state"
    assert not (destination / "manifest.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", "1"),
        ("schema_version", 1.0),
        ("size_bytes", True),
        ("size_bytes", "27"),
        ("size_bytes", 27.0),
    ],
)
def test_manifest_rejects_coerced_numeric_metadata(tmp_path, field, value):
    root = _backup(tmp_path)
    path = root / "manifest.json"
    payload = json.loads(path.read_text())
    if field == "schema_version":
        payload[field] = value
    else:
        payload["components"][0][field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        OperationalBackup().restore(root, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_reparse_ancestor_rejected_without_path_junction_api(tmp_path, monkeypatch):
    import stat
    from types import SimpleNamespace

    root = _backup(tmp_path)
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == tmp_path:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return result

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="junctions"):
        OperationalBackup().restore(root, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize("operation", ["link", "fsync"])
def test_failed_manifest_publication_leaves_no_completion_marker(
    tmp_path, monkeypatch, operation
):
    import edn.intelligence.backup as module

    root = _backup(tmp_path)
    destination = tmp_path / "restored"

    def failed(*args, **kwargs):
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(module.os, operation, failed)
    with pytest.raises(OSError):
        OperationalBackup().restore(root, destination)
    assert not (destination / "manifest.json").exists()
    assert list(destination.glob(".manifest-*")) == []
