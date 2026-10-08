"""Actual website provenance cannot mint a second synthetic receiver item."""

import sys

import pytest

from edn.operations.intake import IntakeStore
from edn.operations.intake_sync import SyntheticSyncError, SyntheticSyncStore
from tests.operations.test_intake import fields


@pytest.mark.parametrize("operation", ["reference_existing", "create_proposal"])
def test_website_approval_cannot_create_receiver_even_with_forged_operation(
    tmp_path, operation
):
    if sys.platform != "linux":
        with pytest.raises(ValueError, match="Linux"):
            IntakeStore(tmp_path / "requests.db").initialise()
        assert tuple(tmp_path.iterdir()) == ()
        return
    root = tmp_path / "intake"
    root.mkdir(mode=0o700)
    receiver = tmp_path / "receiver"
    receiver.mkdir(mode=0o700)
    intake = IntakeStore(root / "requests.db")
    intake.initialise()
    request = intake.import_contract(
        {
            **fields(),
            "source": "EDN Systems Website",
            "contractVersion": "1.0",
            "submittedAt": "2026-10-09T00:00:00Z",
        },
        "SYNTHETIC-EXISTING-1",
        source_identity={
            "source_system": "sharepoint",
            "source_account": "synthetic-account",
            "site_id": "synthetic-site",
            "list_id": "synthetic-list",
            "native_item_id": "SYNTHETIC-EXISTING-1",
        },
    )
    intake.approve(request.request_id, request.revision)
    snapshot = {
        **intake.export(request.request_id, request.revision),
        "not_synced": True,
        "operation": operation,
    }
    before = intake.path.read_bytes()
    sync = SyntheticSyncStore(receiver, intake_store=intake)
    with pytest.raises(SyntheticSyncError):
        sync.deliver(snapshot)
    assert intake.path.read_bytes() == before
    assert not list(receiver.glob("*.json"))
