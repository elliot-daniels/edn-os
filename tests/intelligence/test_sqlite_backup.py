"""Synthetic SQLite/WAL snapshots; no live stores or source credentials."""

from __future__ import annotations

import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import edn.intelligence.backup as module
from edn.intelligence.backup import BackupComponent, OperationalBackup
from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.models import Event
from edn.operations.storage import EventStore


@pytest.fixture
def active_wal(tmp_path):
    source = tmp_path / "operations.db"
    events = EventStore(source)
    events.initialise()
    outcomes = ImportOutcomeStore(source)
    outcomes.initialise()
    writer = sqlite3.connect(source, isolation_level=None)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    main_before = source.read_bytes()
    occurred = datetime(2026, 10, 8, tzinfo=UTC)
    event = Event(
        "outlook",
        "synthetic@example.com",
        "native-wal-record",
        occurred,
        "inbound",
        "email",
        subject="Synthetic record",
        body="Synthetic body",
        raw_payload={"id": "native-wal-record"},
    )
    assert events.insert(event).inserted
    run = outcomes.begin(event.source_account, occurred, occurred + timedelta(days=1))
    outcomes.update(run, inserted=1, duplicates=0, failed=0, pages=1, state="complete")
    assert source.read_bytes() == main_before
    assert Path(str(source) + "-wal").stat().st_size > 0
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE operations_events SET needs_action=1")
    try:
        yield source, event, run
    finally:
        writer.rollback()
        writer.close()


def test_active_wal_snapshot_restores_events_outcomes_provenance_and_replay(
    active_wal, tmp_path
):
    source, event, run = active_wal
    source_before = source.read_bytes()
    wal_before = Path(str(source) + "-wal").read_bytes()
    service = OperationalBackup()
    backup = tmp_path / "backup"
    manifest = service.create(
        backup,
        components=(BackupComponent("operations", source, sqlite_snapshot=True),),
    )
    assert service.verify(backup) == manifest
    restored = tmp_path / "restored"
    assert service.restore(backup, restored) == manifest
    snapshot = restored / manifest.components[0][3]
    with closing(
        sqlite3.connect(f"{snapshot.as_uri()}?mode=ro", uri=True)
    ) as connection:
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    assert EventStore(snapshot, read_only=True).list_events() == (event,)
    outcome = ImportOutcomeStore(snapshot, read_only=True).latest()[0]
    assert (
        outcome.run_id == run and outcome.state == "complete" and outcome.inserted == 1
    )
    replay = EventStore(snapshot).insert(event)
    assert not replay.inserted and replay.event.id == event.id
    assert replay.event.identity_key == event.identity_key
    assert replay.event.raw_payload["id"] == event.external_id
    assert source.read_bytes() == source_before
    assert Path(str(source) + "-wal").read_bytes() == wal_before
    assert not Path(str(snapshot) + "-wal").exists()
    assert not Path(str(snapshot) + "-shm").exists()
    with pytest.raises(FileExistsError):
        service.restore(backup, restored)


def test_sqlite_raw_copy_fails_before_destination_creation(active_wal, tmp_path):
    source, _, _ = active_wal
    destination = tmp_path / "backup"
    with pytest.raises(ValueError, match="explicit consistent"):
        OperationalBackup().create(
            destination, components=(BackupComponent("operations", source),)
        )
    assert not destination.exists()


@pytest.mark.parametrize("flag", [None, 0, 1, "true", []])
def test_snapshot_flag_requires_exact_boolean(tmp_path, flag):
    with pytest.raises(ValueError, match="boolean"):
        BackupComponent("state", tmp_path / "state.db", sqlite_snapshot=flag)


def test_regular_file_backup_and_explicit_wrong_database_fail_closed(tmp_path):
    source = tmp_path / "state.bin"
    source.write_bytes(b"synthetic ordinary file")
    backup = tmp_path / "backup"
    service = OperationalBackup()
    manifest = service.create(backup, components=(BackupComponent("state", source),))
    assert (backup / manifest.components[0][3]).read_bytes() == source.read_bytes()
    invalid = tmp_path / "invalid"
    with pytest.raises(ValueError, match="requires a SQLite"):
        service.create(
            invalid,
            components=(BackupComponent("state", source, sqlite_snapshot=True),),
        )
    assert not invalid.exists()


def test_corrupt_database_has_sanitized_failure_and_no_manifest(tmp_path):
    source = tmp_path / "corrupt.db"
    source.write_bytes(
        b"SQLite format 3\x00" + b"synthetic invalid source detail" * 100
    )
    destination = tmp_path / "backup"
    with pytest.raises(ValueError, match="SQLite snapshot failed safely") as failure:
        OperationalBackup().create(
            destination,
            components=(BackupComponent("state", source, sqlite_snapshot=True),),
        )
    assert "synthetic invalid source detail" not in str(failure.value)
    assert failure.value.__suppress_context__
    assert not (destination / "manifest.json").exists()


@pytest.mark.parametrize("snapshot", [False, True])
@pytest.mark.parametrize("location", ["source", "destination", "ancestor"])
def test_links_and_reparse_paths_rejected_in_both_modes(
    tmp_path, monkeypatch, snapshot, location
):
    source = tmp_path / "state.db"
    if snapshot:
        with closing(sqlite3.connect(source)) as connection:
            connection.execute("CREATE TABLE synthetic(value INTEGER)")
    else:
        source.write_bytes(b"synthetic file")
    destination = tmp_path / "backup"
    flagged = {"source": source, "destination": destination, "ancestor": tmp_path}[
        location
    ]
    original = Path.lstat

    def reparse(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == flagged:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return result

    if location == "destination":
        original_link = Path.is_symlink
        monkeypatch.setattr(
            Path, "is_symlink", lambda path: path == flagged or original_link(path)
        )
    else:
        monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="symlinks or junctions"):
        OperationalBackup().create(
            destination,
            components=(BackupComponent("state", source, sqlite_snapshot=snapshot),),
        )
    assert not destination.exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_linked_sqlite_sidecars_fail_before_opening_database(
    active_wal, tmp_path, monkeypatch, suffix
):
    source, _, _ = active_wal
    flagged = Path(str(source) + suffix)
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == flagged or original(path)
    )
    destination = tmp_path / "backup"
    with pytest.raises(ValueError, match="symlinks or junctions"):
        OperationalBackup().create(
            destination,
            components=(BackupComponent("state", source, sqlite_snapshot=True),),
        )
    assert not destination.exists()


def test_interrupted_snapshot_cannot_publish_or_replace_valid_backup(
    active_wal, tmp_path, monkeypatch
):
    source, _, _ = active_wal
    service = OperationalBackup()
    valid = tmp_path / "valid"
    original = service.create(
        valid, components=(BackupComponent("state", source, sqlite_snapshot=True),)
    )
    bytes_before = {path.name: path.read_bytes() for path in valid.iterdir()}
    real_connect = module.sqlite3.connect

    class Interrupted(sqlite3.Connection):
        def backup(self, target, **kwargs):
            raise KeyboardInterrupt()

    def connect(database, **kwargs):
        if str(database).endswith("?mode=ro"):
            kwargs["factory"] = Interrupted
        return real_connect(database, **kwargs)

    monkeypatch.setattr(module.sqlite3, "connect", connect)
    incomplete = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        service.create(
            incomplete,
            components=(BackupComponent("state", source, sqlite_snapshot=True),),
        )
    assert not (incomplete / "manifest.json").exists()
    with pytest.raises(ValueError, match="missing"):
        service.verify(incomplete)
    assert service.verify(valid) == original
    assert {path.name: path.read_bytes() for path in valid.iterdir()} == bytes_before
    with pytest.raises(FileExistsError):
        service.create(
            valid, components=(BackupComponent("state", source, sqlite_snapshot=True),)
        )


def test_snapshot_deadline_aborts_busy_retries_without_completion(
    active_wal, tmp_path, monkeypatch
):
    source, _, _ = active_wal
    real_connect = module.sqlite3.connect

    class Busy(sqlite3.Connection):
        def backup(self, target, **kwargs):
            kwargs["progress"](sqlite3.SQLITE_BUSY, 1, 1)
            pytest.fail("Expired backup retry was not stopped")

    def connect(database, **kwargs):
        if str(database).endswith("?mode=ro"):
            kwargs["factory"] = Busy
        return real_connect(database, **kwargs)

    clock = iter((0.0, 31.0))
    monkeypatch.setattr(module.sqlite3, "connect", connect)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    destination = tmp_path / "backup"
    with pytest.raises(TimeoutError, match="time bound"):
        OperationalBackup().create(
            destination,
            components=(BackupComponent("state", source, sqlite_snapshot=True),),
        )
    assert not (destination / "manifest.json").exists()


def test_real_exclusive_lock_retries_stop_at_deadline(tmp_path, monkeypatch):
    source = tmp_path / "locked.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE synthetic(value INTEGER)")
        connection.commit()
        connection.execute("BEGIN EXCLUSIVE")
        monkeypatch.setattr(module, "_SQLITE_SNAPSHOT_SECONDS", 0.15)
        destination = tmp_path / "backup"
        with pytest.raises(TimeoutError, match="time bound"):
            OperationalBackup().create(
                destination,
                components=(BackupComponent("state", source, sqlite_snapshot=True),),
            )
        assert not (destination / "manifest.json").exists()


def test_source_replaced_with_sqlite_after_preflight_is_not_raw_copied(
    tmp_path, monkeypatch
):
    source = tmp_path / "state.bin"
    source.write_bytes(b"synthetic regular file")
    original = module._copy_exclusive

    def changed(source_path, target, **kwargs):
        source_path.write_bytes(b"SQLite format 3\x00" + b"synthetic database pages")
        original(source_path, target, **kwargs)

    monkeypatch.setattr(module, "_copy_exclusive", changed)
    destination = tmp_path / "backup"
    with pytest.raises(ValueError, match="explicit consistent"):
        OperationalBackup().create(
            destination, components=(BackupComponent("state", source),)
        )
    assert not (destination / "000-state.bin").exists()
    assert not (destination / "manifest.json").exists()
