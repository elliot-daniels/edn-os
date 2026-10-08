"""Synthetic website fixture intake never implies source access or sync."""

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from edn.operations.intake import (
    APPROVALS_DDL,
    DDL,
    REVISIONS_DDL,
    IntakeError,
    IntakeStore,
)
from tests.operations.test_intake import fields, store


def contract(**changes):
    return {
        **fields(),
        "source": "EDN Systems Website",
        "contractVersion": "1.0",
        "submittedAt": "2026-10-08T00:00:00.000Z",
        **changes,
    }


def test_synthetic_import_provenance_approval_and_replay_preserve_local_edits(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    original = contract()
    imported = requests.import_contract(original, "fixture-one")
    assert imported.state == "draft" and imported.approved_revision is None
    with pytest.raises(IntakeError, match="Approve"):
        requests.export(imported.request_id, 1)
    edited = requests.update(imported.request_id, 1, fields(reference="reviewed"))
    requests.approve(edited.request_id, 2)
    exported = requests.export(edited.request_id, 2)
    assert exported["provenance"] == "synthetic_import"
    assert exported["dry_run"] is True and exported["sync_status"] == "dry_run"
    assert exported["fields"]["Source"] == "EDN Systems Website"
    assert exported["fields"]["SubmittedAt"] == "2026-10-08T00:00:00+00:00"
    assert exported["fields"]["CustomerReference"] == "reviewed"
    replay = IntakeStore(requests.path).import_contract(
        contract(reference="changed"), "fixture-one"
    )
    assert replay.request_id == imported.request_id and replay.revision == 2
    assert replay.fields["reference"] == "reviewed" and replay.state == "approved"
    with sqlite3.connect(requests.path) as connection:
        assert (
            json.loads(
                connection.execute(
                    "SELECT original_payload FROM intake_imports"
                ).fetchone()[0]
            )
            == original
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
    requests = store(tmp_path)
    if requests is None:
        return
    with pytest.raises(IntakeError, match="Invalid synthetic website contract"):
        requests.import_contract(contract(**changes), "fixture-one")
    assert requests.list_requests() == ()


def test_missing_contract_field_identity_and_read_only_fail_without_write(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    missing = contract()
    del missing["phone"]
    with pytest.raises(IntakeError):
        requests.import_contract(missing, "fixture")
    for identity in ("", " invalid", "a\n", 1):
        with pytest.raises(IntakeError):
            requests.import_contract(contract(), identity)
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="Read-only"):
        IntakeStore(requests.path, read_only=True).import_contract(
            contract(), "fixture"
        )
    assert requests.path.read_bytes() == before


def test_concurrent_replay_creates_one_draft_and_one_registry_record(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    with ThreadPoolExecutor(max_workers=4) as workers:
        imported = list(
            workers.map(
                lambda _: IntakeStore(requests.path).import_contract(
                    contract(), "same"
                ),
                range(8),
            )
        )
    assert len({request.request_id for request in imported}) == 1
    assert all(request.state == "draft" for request in imported)
    assert len(requests.list_requests()) == 1


def test_explicit_upgrade_preserves_existing_manual_rows_and_readonly_version1(
    tmp_path,
):
    if os.name != "posix":
        assert store(tmp_path) is None
        return
    tmp_path.chmod(0o700)
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(DDL)
        connection.execute(REVISIONS_DDL)
        connection.execute(APPROVALS_DDL)
        connection.execute("PRAGMA user_version=1")
    path.chmod(0o600)
    requests = IntakeStore(path)
    manual = requests.create(fields())
    before = path.read_bytes()
    with pytest.raises(IntakeError, match="explicitly"):
        requests.import_contract(contract(), "fixture")
    assert path.read_bytes() == before
    assert IntakeStore(path, read_only=True).get(manual.request_id) == manual
    requests.initialise()
    assert requests.get(manual.request_id) == manual
    requests.import_contract(contract(), "fixture")
    assert len(requests.list_requests()) == 2


def test_legacy_upgrade_rolls_back_on_injected_failure(tmp_path, monkeypatch):
    from edn.operations import intake

    if os.name != "posix":
        assert store(tmp_path) is None
        return
    tmp_path.chmod(0o700)
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(DDL)
        connection.execute(REVISIONS_DDL)
        connection.execute(APPROVALS_DDL)
        connection.execute("PRAGMA user_version=1")
    path.chmod(0o600)
    before = path.read_bytes()
    monkeypatch.setattr(intake, "IMPORTS_DDL", "CREATE TABLE malformed (")
    with pytest.raises(sqlite3.OperationalError):
        IntakeStore(path).initialise()
    assert path.read_bytes() == before


def test_surrogate_fixture_has_fixed_error_without_write(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="Invalid synthetic website contract"):
        requests.import_contract(contract(jobDescription="\ud800"), "fixture")
    assert requests.path.read_bytes() == before
