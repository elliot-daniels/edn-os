"""Synthetic local Work Intake approval and exact website mapping boundaries."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, IntakeStore, validate_fields


def fields(**changes):
    return {
        "contactName": "Alex Smith",
        "company": "Example",
        "email": "A@example.com",
        "phone": "+61 400 000 000",
        "siteLocation": "Adelaide",
        "serviceRequired": "Field engineering",
        "preferredDate": "",
        "urgency": "Routine",
        "jobDescription": "Inspect the network",
        "reference": "PO-123",
        **changes,
    }


def store(tmp_path):
    result = IntakeStore(tmp_path / "requests.db")
    result.initialise()
    return result


def test_review_approve_dry_run_edit_restart_and_exact_mapping(tmp_path):
    requests = store(tmp_path)
    request = requests.create(fields())
    assert request.state == "draft" and request.sync_status == "not_synced"
    with pytest.raises(IntakeError, match="Approve"):
        requests.export(request.request_id, 1)
    requests.approve(request.request_id, 1)
    exported = requests.export(request.request_id, 1)
    assert exported == {
        "request_id": request.request_id,
        "revision": 1,
        "dry_run": True,
        "sync_status": "dry_run",
        "fields": {
            "Title": "Pending",
            "ContactName": "Alex Smith",
            "Company": "Example",
            "Email": "a@example.com",
            "Phone": "+61400000000",
            "Site_x002f_Location": "Adelaide",
            "ServiceRequired": "Field engineering",
            "Urgency": "Routine",
            "JobDescription": "Inspect the network",
            "CustomerReference": "PO-123",
            "Source": "EDN OS Manual",
            "SubmittedAt": request.created_at,
            "ContractVersion": "1.0",
            "Status": "New",
        },
    }
    restarted = IntakeStore(requests.path)
    assert restarted.get(request.request_id).sync_status == "dry_run"
    changed = restarted.update(
        request.request_id, 1, fields(preferredDate="2026-10-30")
    )
    assert changed.revision == 2 and changed.state == "draft"
    assert changed.approved_revision is None and changed.sync_status == "not_synced"
    with pytest.raises(IntakeError):
        restarted.export(request.request_id, 2)
    restarted.approve(request.request_id, 2)
    assert (
        restarted.export(request.request_id, 2)["fields"]["PreferredDate"]
        == "2026-10-30"
    )
    with sqlite3.connect(requests.path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM intake_revisions"
        ).fetchone() == (2,)
        original = json.loads(
            connection.execute(
                "SELECT fields FROM intake_revisions WHERE revision=1"
            ).fetchone()[0]
        )
        assert original["preferredDate"] == ""


@pytest.mark.parametrize(
    "change",
    [
        {"contactName": ""},
        {"email": "bad"},
        {"phone": "short"},
        {"serviceRequired": "invented"},
        {"urgency": "Invented"},
        {"preferredDate": "2026-02-31"},
        {"jobDescription": "x" * 4001},
        {"company": 12},
        {"Title": "injected"},
        {"source": "Website"},
    ],
)
def test_invalid_input_rejected_without_creating_requests(tmp_path, change):
    requests = store(tmp_path)
    with pytest.raises(IntakeError):
        requests.create(fields(**change))
    assert requests.list_requests() == ()


def test_attachments_are_local_exact_request_and_invalidate_approval(tmp_path):
    requests = store(tmp_path)
    first, other = requests.create(fields()), requests.create(fields())
    attachment = {
        "attachment_id": str(uuid4()),
        "request_id": first.request_id,
        "original_name": "plan.pdf",
        "media_type": "application/pdf",
        "size_bytes": 100,
        "sha256": "a" * 64,
    }
    requests.approve(first.request_id, 1)
    changed = requests.update(
        first.request_id, 1, first.fields, attachments=[attachment]
    )
    assert changed.state == "draft" and changed.attachments == (attachment,)
    with pytest.raises(IntakeError):
        requests.update(other.request_id, 1, other.fields, attachments=[attachment])
    assert requests.get(other.request_id).revision == 1
    requests.approve(first.request_id, 2)
    assert "attachments" not in requests.export(first.request_id, 2)["fields"]


def test_stale_revision_updates_have_one_winner_and_no_cross_request_change(tmp_path):
    requests = store(tmp_path)
    request, neighbor = requests.create(fields()), requests.create(fields())

    def edit(index):
        try:
            return IntakeStore(requests.path).update(
                request.request_id, 1, fields(reference=str(index))
            )
        except IntakeError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(edit, range(2)))
    assert sum(value is not None for value in outcomes) == 1
    assert requests.get(neighbor.request_id) == neighbor
    for action in (requests.approve, requests.export):
        with pytest.raises(IntakeError, match="reload"):
            action(request.request_id, 1)


def test_read_only_and_missing_store_never_create_or_modify(tmp_path):
    missing = tmp_path / "missing.db"
    reader = IntakeStore(missing, read_only=True)
    with pytest.raises(IntakeError):
        reader.initialise()
    with pytest.raises(sqlite3.OperationalError):
        reader.list_requests()
    assert not missing.exists()
    requests = store(tmp_path)
    request = requests.create(fields())
    before = requests.path.read_bytes()
    reader = IntakeStore(requests.path, read_only=True)
    for action in (
        lambda: reader.create(fields()),
        lambda: reader.update(request.request_id, 1, fields()),
        lambda: reader.approve(request.request_id, 1),
        lambda: reader.export(request.request_id, 1),
    ):
        with pytest.raises(IntakeError, match="Read-only"):
            action()
    assert requests.path.read_bytes() == before


def test_corrupt_or_unknown_store_rejects_without_adoption(tmp_path):
    requests = store(tmp_path)
    request = requests.create(fields())
    requests.approve(request.request_id, 1)
    with sqlite3.connect(requests.path) as connection:
        connection.execute(
            "UPDATE intake_revisions SET fields=?",
            (json.dumps(validate_fields(fields(reference="tampered"))),),
        )
    with pytest.raises(IntakeError, match="invalid"):
        requests.export(request.request_id, 1)
    with sqlite3.connect(requests.path) as connection:
        connection.execute("PRAGMA user_version=9")
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="schema"):
        requests.initialise()
    assert requests.path.read_bytes() == before


def test_queue_pages_preserve_all_requests_and_reject_invalid_bounds(tmp_path):
    requests = store(tmp_path)
    created = {requests.create(fields()).request_id for _ in range(5)}
    rows = (
        requests.list_requests(limit=2)
        + requests.list_requests(limit=2, offset=2)
        + requests.list_requests(limit=2, offset=4)
    )
    assert {row.request_id for row in rows} == created
    for options in ({"limit": 0}, {"offset": -1}, {"limit": True}):
        with pytest.raises(IntakeError):
            requests.list_requests(**options)
