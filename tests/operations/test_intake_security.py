"""Native fail-closed protection and explicit self-approval audit evidence."""

import os
import stat

import pytest

from edn.operations.intake import IntakeStore
from edn.operations.intake_security import (
    IntakeSecurityError,
    protect_file,
    request_lock,
    validate_root,
)
from tests.operations.test_intake import fields, store


def test_native_unsupported_storage_all_entrypoints_do_not_touch_files(tmp_path):
    if os.name == "posix":
        tmp_path.chmod(0o700)
        assert validate_root(tmp_path) == tmp_path
        return
    path = tmp_path / "requests.db"
    requests = IntakeStore(path)
    for action in (
        requests.initialise,
        requests.list_requests,
        lambda: requests.create(fields()),
    ):
        with pytest.raises(IntakeSecurityError, match="Linux or WSL"):
            action()
    assert not path.exists() and tuple(tmp_path.iterdir()) == ()


def test_owned_modes_links_and_self_approval_audit(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    assert stat.S_IMODE(requests.path.stat().st_mode) == 0o600
    request = requests.create(fields())
    approved = requests.approve(request.request_id, 1)
    assert "self-approval" in approved.approval_actor
    assert approved.approval_timestamp
    audit = requests.audit_history(request.request_id)
    assert audit[0]["revision"] == 1 and audit[0]["decision"] == "approved"
    requests.update(request.request_id, 1, fields(reference="changed"))
    assert requests.audit_history(request.request_id) == audit
    assert requests.get(request.request_id).approval_actor is None
    link = tmp_path / "hardlink.db"
    os.link(requests.path, link)
    with pytest.raises(IntakeSecurityError):
        requests.list_requests()
    link.unlink()
    requests.path.chmod(0o644)
    with pytest.raises(IntakeSecurityError):
        requests.list_requests()
    requests.path.chmod(0o600)
    alias = tmp_path / "alias.db"
    alias.symlink_to(requests.path)
    with pytest.raises(OSError):
        protect_file(alias)
    with request_lock(tmp_path, request.request_id):
        assert (
            stat.S_IMODE((tmp_path / (request.request_id + ".lock")).stat().st_mode)
            == 0o600
        )


def test_unsafe_root_fails_before_create(tmp_path):
    if os.name != "posix":
        assert store(tmp_path) is None
        return
    tmp_path.chmod(0o755)
    with pytest.raises(IntakeSecurityError):
        IntakeStore(tmp_path / "requests.db").initialise()
    assert not (tmp_path / "requests.db").exists()


def test_contract_validation_runs_on_every_platform():
    from edn.operations.intake import validate_fields

    assert validate_fields(fields())["email"] == "a@example.com"
    with pytest.raises(ValueError):
        validate_fields(fields(jobDescription="\ud800"))


def test_missing_store_read_has_fixed_database_error_without_private_path(tmp_path):
    import sqlite3
    import traceback

    if os.name != "posix":
        assert store(tmp_path) is None
        return
    tmp_path.chmod(0o700)
    path = tmp_path / "synthetic-private-request-store.db"
    with pytest.raises(sqlite3.OperationalError) as raised:
        IntakeStore(path, read_only=True).list_requests()
    assert str(raised.value) == "Request store is unavailable"
    assert str(path) not in "".join(traceback.format_exception(raised.value))
    assert not path.exists()
