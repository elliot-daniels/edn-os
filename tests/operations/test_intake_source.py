"""Synthetic source identity, change review and potential duplicate work."""

import json
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, IntakeStore, _source_contract
from tests.operations.test_intake import fields, store


def contract(**changes):
    return {
        **fields(),
        "contractVersion": "1.0",
        "source": "EDN Systems Website",
        "submittedAt": "2026-10-09T00:00:00Z",
        **changes,
    }


def identity(native="1", **changes):
    return {
        "source_system": "sharepoint",
        "source_account": "synthetic-account",
        "site_id": "synthetic-site",
        "list_id": "synthetic-list",
        "native_item_id": native,
        **changes,
    }


def test_source_tuple_replay_and_native_fields_reference_existing_export(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    replay = IntakeStore(requests.path).import_contract(
        contract(), "1", source_identity=identity()
    )
    assert (
        replay.request_id == imported.request_id
        and replay.revision == 1
        and replay.state == "draft"
    )
    requests.approve(imported.request_id, 1)
    exported = requests.export(imported.request_id, 1)
    assert exported["operation"] == "reference_existing"
    assert exported["target"]["native_item_id"] == "1"
    assert exported["target"]["site_id"] == "synthetic-site"
    assert exported["source_provenance"]["synthetic_only"] is True
    assert exported["fields"]["Source"] == "EDN Systems Website"
    assert exported["fields"]["SubmittedAt"] == "2026-10-09T00:00:00+00:00"
    other = requests.import_contract(
        contract(reference="other"),
        "1",
        source_identity=identity(site_id="other-synthetic-site"),
    )
    assert other.request_id != imported.request_id


def test_changed_source_preserves_corrections_and_requires_explicit_resolution(
    tmp_path,
):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    corrected = requests.update(
        imported.request_id, 1, fields(reference="local correction")
    )
    requests.approve(imported.request_id, corrected.revision)
    changed = requests.import_contract(
        contract(jobDescription="changed source"), "1", source_identity=identity()
    )
    assert (
        changed.state == "draft"
        and changed.source_pending
        and changed.fields["reference"] == "local correction"
    )
    assert (
        requests.audit_history(changed.request_id)[-1]["decision"] == "source_changed"
    )
    with pytest.raises(IntakeError, match="source facts"):
        requests.approve(changed.request_id, changed.revision)
    resolved = requests.resolve_source_change(
        changed.request_id,
        changed.revision,
        decision="keep_local",
        reason="Reviewed source; keep operator correction",
    )
    assert (
        not resolved.source_pending
        and resolved.fields["reference"] == "local correction"
    )
    requests.approve(resolved.request_id, resolved.revision)
    with requests._connect() as connection:
        history = connection.execute(
            "SELECT payload FROM intake_source_history ORDER BY source_revision"
        ).fetchall()
    assert json.loads(history[0][0]) == contract()
    assert json.loads(history[1][0])["jobDescription"] == "changed source"


def test_potential_cross_source_duplicates_require_explicit_distinct_or_same_work(
    tmp_path,
):
    requests = store(tmp_path)
    if requests is None:
        return
    manual = requests.create(fields(), submission_id=str(uuid4()))
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    assert requests.duplicate_candidates(imported.request_id) == (manual,)
    with pytest.raises(IntakeError, match="duplicate"):
        requests.approve(imported.request_id, 1)
    requests.resolve_duplicate(
        imported.request_id,
        manual.request_id,
        1,
        decision="same_work",
        reason="Same underlying synthetic work",
    )
    canonical = requests.get(manual.request_id)
    alias = requests.get(imported.request_id)
    assert (
        len(requests.list_requests()) == 2 and canonical.state == alias.state == "draft"
    )
    with pytest.raises(IntakeError, match="Linked"):
        requests.approve(alias.request_id, alias.revision)
    requests.approve(canonical.request_id, canonical.revision)
    exported = requests.export(canonical.request_id, canonical.revision)
    assert exported["idempotency_key"]
    assert exported["operation"] == "reference_existing"
    with pytest.raises(IntakeError):
        requests.export(alias.request_id, alias.revision)


def test_independent_keys_same_content_can_be_confirmed_distinct(tmp_path):
    requests = store(tmp_path)
    if requests is None:
        return
    one = requests.create(fields(), submission_id=str(uuid4()))
    two = requests.create(fields(), submission_id=str(uuid4()))
    requests.resolve_duplicate(
        one.request_id,
        two.request_id,
        1,
        decision="distinct",
        reason="Two distinct jobs with identical submitted details",
    )
    requests.approve(one.request_id, 1)
    requests.approve(two.request_id, 1)
    assert one.request_id != two.request_id and len(requests.list_requests()) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "manual"},
        {"contractVersion": "2"},
        {"submittedAt": "not-time"},
        {"extra": "not allowed"},
    ],
)
def test_pure_invalid_source_contract_has_fixed_error(changes):
    with pytest.raises(IntakeError, match="synthetic website"):
        _source_contract(contract(**changes))


def test_corrupt_source_identity_blocks_direct_get_and_export(tmp_path):
    import sqlite3

    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    with sqlite3.connect(requests.path) as connection:
        connection.execute("UPDATE intake_sources SET identity='{}'")
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="provenance"):
        requests.get(imported.request_id)
    assert requests.path.read_bytes() == before


def test_version_two_upgrade_preserves_manual_receipts_and_audits(tmp_path):
    from edn.operations.intake import BASE_APPROVALS_DDL

    requests = store(tmp_path)
    if requests is None:
        return
    intent = requests.begin_submission()
    original = requests.create(fields(), submission_id=intent.submission_id)
    approved = requests.approve(original.request_id, 1)
    history = requests.audit_history(original.request_id)
    with requests._connect() as connection:
        for table in (
            "intake_source_history",
            "intake_sources",
            "intake_duplicate_decisions",
            "intake_work_links",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("ALTER TABLE intake_approvals RENAME TO old_audit")
        connection.execute(BASE_APPROVALS_DDL)
        connection.execute(
            "INSERT INTO intake_approvals SELECT * FROM old_audit ORDER BY rowid"
        )
        connection.execute("DROP TABLE old_audit")
        connection.execute("PRAGMA user_version=2")
    assert requests.get(original.request_id) == approved
    requests.initialise()
    assert requests.get(original.request_id) == approved
    assert requests.audit_history(original.request_id) == history
    assert requests.current_submission().submission_id == intent.submission_id
    imported = requests.import_contract(
        contract(reference="separate"), "1", source_identity=identity()
    )
    assert imported.request_id != original.request_id


def test_cancelled_source_update_does_not_resurrect_and_linked_alias_cannot_edit(
    tmp_path,
):
    requests = store(tmp_path)
    if requests is None:
        return
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    cancelled = requests.transition(
        imported.request_id, 1, "cancelled", reason="Operator canceled this intake"
    )
    changed = requests.import_contract(
        contract(reference="upstream changed"), "1", source_identity=identity()
    )
    assert (
        changed.state == "cancelled"
        and changed.revision == cancelled.revision
        and changed.source_pending
    )
    with pytest.raises(IntakeError):
        requests.resolve_source_change(
            changed.request_id,
            changed.revision,
            decision="apply_source",
            reason="Must not reopen canceled work",
        )
    with pytest.raises(IntakeError):
        requests.approve(changed.request_id, changed.revision)
    manual = requests.create(fields(reference="other work"), submission_id=str(uuid4()))
    alias = requests.import_contract(
        contract(reference="other work"), "2", source_identity=identity("2")
    )
    requests.resolve_duplicate(
        alias.request_id,
        manual.request_id,
        1,
        decision="same_work",
        reason="Same existing work",
    )
    alias = requests.get(alias.request_id)
    with pytest.raises(IntakeError, match="canonical"):
        requests.update(
            alias.request_id, alias.revision, fields(reference="new correction")
        )


def test_source_preview_is_latest_validated_readonly_and_alias_has_canonical_id(
    tmp_path,
):
    requests = store(tmp_path)
    if requests is None:
        return
    manual = requests.create(fields(), submission_id=str(uuid4()))
    imported = requests.import_contract(contract(), "1", source_identity=identity())
    requests.resolve_duplicate(
        imported.request_id,
        manual.request_id,
        1,
        decision="same_work",
        reason="Explicit existing work link",
    )
    changed = requests.import_contract(
        contract(jobDescription="Proposed changed source details"),
        "1",
        source_identity=identity(),
    )
    reader = IntakeStore(requests.path, read_only=True)
    before = requests.path.read_bytes()
    preview = reader.source_snapshot(changed.request_id)
    assert preview["jobDescription"] == "Proposed changed source details"
    assert (
        preview["source"] == "EDN Systems Website"
        and preview["contractVersion"] == "1.0"
    )
    provenance = reader.source_provenance(changed.request_id)
    assert (
        provenance["canonical_work_id"] == manual.request_id
        and provenance["linked_alias"] is True
    )
    assert requests.path.read_bytes() == before


@pytest.mark.parametrize("terminal", ["cancelled", "rejected"])
def test_linked_source_change_preserves_canonical_terminal_state(tmp_path, terminal):
    requests = store(tmp_path)
    if requests is None:
        return
    canonical = requests.create(fields(), submission_id=str(uuid4()))
    alias = requests.import_contract(contract(), "1", source_identity=identity())
    requests.resolve_duplicate(
        alias.request_id,
        canonical.request_id,
        1,
        decision="same_work",
        reason="Linked existing synthetic work",
    )
    canonical = requests.get(canonical.request_id)
    terminal_request = requests.transition(
        canonical.request_id,
        canonical.revision,
        terminal,
        reason="Explicit operator terminal decision",
    )
    history = requests.audit_history(canonical.request_id)
    changed = requests.import_contract(
        contract(jobDescription="Changed source after terminal decision"),
        "1",
        source_identity=identity(),
    )
    assert changed.source_pending and changed.state == "draft"
    assert requests.get(canonical.request_id) == terminal_request
    assert requests.audit_history(canonical.request_id) == history
    for action in (requests.approve, requests.export):
        with pytest.raises(IntakeError):
            action(canonical.request_id, terminal_request.revision)
    for decision in ("keep_local", "apply_source"):
        before = requests.path.read_bytes()
        with pytest.raises(IntakeError, match="Reopen canonical"):
            requests.resolve_source_change(
                alias.request_id,
                changed.revision,
                decision=decision,
                reason="Must not silently reopen terminal work",
            )
        assert requests.path.read_bytes() == before
    assert requests.get(alias.request_id).source_pending
    if terminal == "rejected":
        reopened = requests.transition(
            canonical.request_id,
            terminal_request.revision,
            "draft",
            reason="Explicit legal operator reopening",
        )
        resolved = requests.resolve_source_change(
            alias.request_id,
            changed.revision,
            decision="keep_local",
            reason="Review source after audited reopening",
        )
        assert not resolved.source_pending
        assert requests.get(canonical.request_id) == reopened


@pytest.mark.parametrize("terminal", ["cancelled", "rejected"])
def test_same_work_resolver_does_not_reopen_terminal_canonical_request(
    tmp_path, terminal
):
    requests = store(tmp_path)
    if requests is None:
        return
    canonical = requests.create(fields(), submission_id=str(uuid4()))
    alias = requests.import_contract(contract(), "1", source_identity=identity())
    terminal_request = requests.transition(
        canonical.request_id, 1, terminal, reason="Operator terminal decision"
    )
    before = requests.path.read_bytes()
    with pytest.raises(IntakeError, match="Reopen"):
        requests.resolve_duplicate(
            alias.request_id,
            canonical.request_id,
            1,
            decision="same_work",
            reason="Must not override the terminal decision",
        )
    assert requests.path.read_bytes() == before
    assert requests.get(canonical.request_id) == terminal_request
