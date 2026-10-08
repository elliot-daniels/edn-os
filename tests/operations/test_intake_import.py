"""Ported original synthetic intake regressions for explicit native source review."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from edn.operations.intake import (
    BASE_APPROVALS_DDL,
    IntakeError,
    IntakeStore,
    _source_contract,
)
from tests.operations.test_intake import fields, store
from tests.operations.test_intake_source import contract, identity


def _legacy_snapshot(requests, version):
    with requests._connect() as connection:
        for table in (
            "intake_source_history",
            "intake_sources",
            "intake_duplicate_decisions",
            "intake_work_links",
        ):
            connection.execute(f"DROP TABLE {table}")
        if version == 1:
            connection.execute("DROP TABLE intake_intent")
            connection.execute("DROP TABLE intake_submissions")
        connection.execute("ALTER TABLE intake_approvals RENAME TO previous_audit")
        connection.execute(BASE_APPROVALS_DDL)
        connection.execute(
            "INSERT INTO intake_approvals SELECT * FROM previous_audit ORDER BY rowid"
        )
        connection.execute("DROP TABLE previous_audit")
        connection.execute(f"PRAGMA user_version={version}")


def test_synthetic_import_provenance_and_same_facts_replay_preserve_local_edits(
    tmp_path,
):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(
        contract(), "fixture-one", source_identity=identity("fixture-one")
    )
    edited = requests.update(imported.request_id, 1, fields(reference="reviewed"))
    requests.approve(edited.request_id, edited.revision)
    replay = IntakeStore(requests.path).import_contract(
        contract(), "fixture-one", source_identity=identity("fixture-one")
    )
    assert replay.request_id == imported.request_id and replay.revision == 2
    assert replay.fields["reference"] == "reviewed" and replay.state == "approved"
    exported = requests.export(replay.request_id, replay.revision)
    assert (
        exported["operation"] == "reference_existing"
        and exported["source_provenance"]["synthetic_only"]
    )
    with requests._connect() as connection:
        assert (
            json.loads(
                connection.execute(
                    "SELECT payload FROM intake_source_history"
                ).fetchone()[0]
            )
            == contract()
        )
        assert connection.execute(
            "SELECT count(*) FROM intake_requests"
        ).fetchone() == (1,)


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "EDN OS Manual"},
        {"contractVersion": "2.0"},
        {"submittedAt": "2026-10-08"},
        {"submittedAt": "2026-10-08T00:00:00+10:00"},
        {"submittedAt": "sensitive-invalid"},
        {"unknown": "value"},
        {"jobDescription": "x" * 4001},
        {"contactName": ""},
    ],
)
def test_invalid_fixture_never_creates_or_approves_request(tmp_path, changes):
    with pytest.raises(IntakeError, match="Invalid synthetic website contract"):
        _source_contract(contract(**changes))
    requests = store(tmp_path)
    if requests is None:
        return
    with pytest.raises(IntakeError):
        requests.import_contract(
            contract(**changes), "fixture", source_identity=identity("fixture")
        )
    assert requests.list_requests() == ()


def test_missing_contract_identity_and_readonly_failure_never_write(tmp_path):
    missing = contract()
    del missing["phone"]
    with pytest.raises(IntakeError):
        _source_contract(missing)
    requests = store(tmp_path)
    if requests is None:
        return
    for native in ("", " invalid", "a\n", 1):
        with pytest.raises(IntakeError):
            requests.import_contract(
                contract(), native, source_identity=identity(native)
            )
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="Read-only"):
        IntakeStore(requests.path, read_only=True).import_contract(
            contract(), "fixture", source_identity=identity("fixture")
        )
    assert requests.path.read_bytes() == before


def test_concurrent_eight_replays_create_one_draft_registry_and_history(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    with ThreadPoolExecutor(max_workers=4) as workers:
        imported = list(
            workers.map(
                lambda _: IntakeStore(requests.path).import_contract(
                    contract(), "same", source_identity=identity("same")
                ),
                range(8),
            )
        )
    assert len({item.request_id for item in imported}) == 1
    assert all(item.state == "draft" for item in imported)
    with requests._connect() as connection:
        assert connection.execute("SELECT count(*) FROM intake_sources").fetchone() == (
            1,
        )
        assert connection.execute(
            "SELECT count(*) FROM intake_source_history"
        ).fetchone() == (1,)


@pytest.mark.parametrize("version", [1, 2])
def test_explicit_upgrade_preserves_manual_rows_and_readonly_legacy(tmp_path, version):
    requests = store(tmp_path)
    if requests is None:
        return
    manual = requests.create(fields(), submission_id=str(uuid4()))
    history = requests.audit_history(manual.request_id)
    _legacy_snapshot(requests, version)
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="explicitly"):
        requests.import_contract(
            contract(), "fixture", source_identity=identity("fixture")
        )
    assert requests.path.read_bytes() == before
    assert IntakeStore(requests.path, read_only=True).get(manual.request_id) == manual
    requests.initialise()
    assert requests.get(manual.request_id) == manual
    assert requests.audit_history(manual.request_id) == history
    requests.import_contract(
        contract(reference="independent"),
        "fixture",
        source_identity=identity("fixture"),
    )
    assert len(requests.list_requests()) == 2


def test_legacy_upgrade_failure_preserves_original_snapshot(tmp_path, monkeypatch):
    from edn.operations import intake

    requests = store(tmp_path)
    if requests is None:
        return
    requests.create(fields(), submission_id=str(uuid4()))
    _legacy_snapshot(requests, 2)
    before = requests.path.read_bytes()
    monkeypatch.setattr(intake, "SOURCE_DDL", "CREATE TABLE malformed (")
    with pytest.raises(sqlite3.OperationalError):
        requests.initialise()
    assert requests.path.read_bytes() == before


def test_surrogate_and_body_bounds_have_fixed_diagnostics_without_write(tmp_path):
    for payload in (
        contract(jobDescription="\ud800"),
        contract(submittedAt="x" * 32769),
    ):
        with pytest.raises(IntakeError, match="Invalid synthetic website contract"):
            _source_contract(payload)
    requests = store(tmp_path)
    if requests is None:
        return
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError):
        requests.import_contract(
            contract(jobDescription="\ud800"),
            "fixture",
            source_identity=identity("fixture"),
        )
    assert requests.path.read_bytes() == before
