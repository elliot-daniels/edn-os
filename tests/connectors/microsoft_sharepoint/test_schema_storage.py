"""Synthetic storage tests; no authentication, real ACL edits, or network."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest

from edn.connectors.microsoft_sharepoint import schema_launch as m
from edn.connectors.microsoft_sharepoint.schema_executor import (
    SchemaExecutor,
    SchemaIdentity,
    SchemaInspectionError,
)


def evidence(child=False):
    admin = "S-1-5-21-2158520141-276418557-3228345628-1001"
    return dict(
        execution_sid=m.EXECUTION_SID,
        owner_sid=m.EXECUTION_SID if child else m.PREPARATION_SID,
        protected=not child,
        admin_sid=admin,
        rules=[
            dict(
                sid=sid,
                rights=rights,
                type="Allow",
                inherited=child,
                inheritance=3,
                propagation=0,
            )
            for sid, rights in [
                ("S-1-5-18", 2032127),
                ("S-1-5-32-544", 2032127),
                (admin, 2032127),
                (m.EXECUTION_SID, 1245631),
            ]
        ],
    )


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "OUTPUT", tmp_path)
    monkeypatch.setattr(m, "inspect_acl", lambda p: evidence(p != tmp_path))
    return tmp_path


def test_two_runs_unique_probe_cleanup_and_no_retention(root):
    first, second = m.prepare_run(), m.prepare_run()
    assert first != second
    assert first.parent == second.parent == root
    assert list(first.iterdir()) == list(second.iterdir()) == []


@pytest.mark.parametrize("nonempty", [False, True])
def test_collision_never_reuses_existing_child(root, monkeypatch, nonempty):
    monkeypatch.setattr(m, "uuid4", lambda: UUID(int=1))
    child = root / ("run-" + UUID(int=1).hex)
    child.mkdir()
    if nonempty:
        (child / "previous").write_text("unchanged")
    with pytest.raises(SchemaInspectionError, match="storage_run_collision_or_denied"):
        m.prepare_run()
    assert child.exists()
    if nonempty:
        assert (child / "previous").read_text() == "unchanged"


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "C:\\escape",
        "..",
        "run-abc",
        "run-" + ("a" * 32) + ":stream",
        "run-" + ("A" * 32),
    ],
)
def test_invalid_child_names(root, name):
    with pytest.raises(SchemaInspectionError):
        m.check_run_path(root / name)


def test_outside_and_canonical_traversal(root):
    child = m.prepare_run()
    with pytest.raises(SchemaInspectionError):
        m.check_run_path(root / ".." / root.name / child.name)
    outside = root.parent / child.name
    outside.mkdir()
    with pytest.raises(SchemaInspectionError, match="storage_containment"):
        m.check_run_path(outside)


def test_reparse_rejected(root, monkeypatch):
    child = m.prepare_run()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p == child or original(p))
    with pytest.raises(SchemaInspectionError, match="storage_reparse"):
        m.check_run_path(child)


def test_existing_nonempty_child_blocks_and_parent_can_contain_older_runs(root):
    child = m.prepare_run()
    (child / "old").write_text("deadline unchanged")
    with pytest.raises(
        SchemaInspectionError, match="storage_not_empty_or_prior_attempt"
    ):
        m.check_storage(child)
    fresh = m.prepare_run()
    assert fresh != child
    assert (child / "old").read_text() == "deadline unchanged"


@pytest.mark.parametrize("child", [False, True])
def test_exact_acl(child):
    m.validate_acl(evidence(child), child=child)
    value = evidence(child)
    value["rules"][0]["sid"] = "S-1-1-0"
    with pytest.raises(SchemaInspectionError):
        m.validate_acl(value, child=child)


def test_acl_unavailable_prevents_auth(root, monkeypatch):
    monkeypatch.setattr(
        m,
        "inspect_acl",
        Mock(side_effect=SchemaInspectionError("storage_acl_unavailable")),
    )
    auth = Mock()
    monkeypatch.setattr(m, "authenticate", auth)
    with pytest.raises(SchemaInspectionError, match="storage_acl_unavailable"):
        m.launch()
    auth.assert_not_called()
    assert list(root.iterdir()) == []


def test_acl_inspection_readonly_failure(monkeypatch, tmp_path):
    runner = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(m.subprocess, "run", runner)
    with pytest.raises(SchemaInspectionError, match="storage_acl_unavailable"):
        m.inspect_acl(tmp_path)
    command = runner.call_args.args[0][-1]
    assert "Get-Acl" in command
    assert "Set-Acl" not in command and "icacls" not in command


def test_probe_read_failure_still_deletes(root, monkeypatch):
    child = m.prepare_run()
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=OSError()))
    with pytest.raises(SchemaInspectionError, match="storage_probe_failed"):
        m.storage_probe(child)
    assert list(child.iterdir()) == []


def test_probe_delete_failure_fails_closed(root, monkeypatch):
    child = m.prepare_run()
    monkeypatch.setattr(Path, "unlink", Mock(side_effect=OSError()))
    with pytest.raises(SchemaInspectionError, match="storage_probe_cleanup_failed"):
        m.storage_probe(child)
    assert len(list(child.iterdir())) == 1


def test_retention_manifest_and_previous_deadline_unchanged(root):
    identity = SchemaIdentity(
        m.TENANT, m.APPLICATION, m.ACCOUNT, frozenset({"Sites.Selected"}), m.GRANT_ID
    )
    artifacts = []
    for _ in range(2):
        child = m.prepare_run()
        transport = Mock()
        transport.get.side_effect = SchemaInspectionError("synthetic_failure")
        with pytest.raises(SchemaInspectionError):
            SchemaExecutor(identity, transport).run(child)
        transport.get.assert_called_once()
        path = child / "schema-inspection.json"
        manifest = json.loads(path.read_text())
        assert manifest["run_id"] == child.name
        assert manifest["artifact_created_at"] == manifest["started_at"]
        assert datetime.fromisoformat(manifest["delete_by"]) - datetime.fromisoformat(
            manifest["started_at"]
        ) == timedelta(days=7)
        digest = manifest.pop("manifest_content_sha256")
        assert (
            digest
            == hashlib.sha256(
                json.dumps(
                    manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
        )
        artifacts.append((path, path.read_bytes()))
    assert artifacts[0][0].read_bytes() == artifacts[0][1]
