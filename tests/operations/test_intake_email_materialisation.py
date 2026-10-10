"""Canonical email jobs preserve provenance and existing security/review gates."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

from edn.operations.intake import IntakeError, IntakeStore, _record_contract
from tests.operations.test_intake import store as request_store
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_drafts import store as draft_store
from tests.operations.test_intake_source import contract, identity

BODY = """Contact: Synthetic Operator
Customer: Synthetic Co
Email: synthetic@example.test
Phone: 0400000000
Site: Synthetic depot
Scope: Replace failed switch
Job reference: SYNTH-123
Duration: 90 minutes"""


def stores(tmp_path):
    drafts = draft_store(tmp_path)
    if drafts is None:
        return None, None
    return drafts, request_store(tmp_path)


def test_canonical_create_restart_replay_and_email_dry_run_provenance(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    draft = drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    assert job.source_type == "synthetic_email" and job.state == "draft"
    assert job.fields["jobDescription"] == "Replace failed switch"
    assert requests.list_requests() == (job,)
    reopened = IntakeStore(requests.path)
    assert drafts.materialise(source.identity_key, 1, reopened) == job
    requests.approve(job.request_id, 1)
    exported = requests.export(job.request_id, 1)
    receipt = exported["source_provenance"]["email_receipt"]
    assert receipt["source_hash"] == draft["source_hash"]
    assert receipt["event_source_key"] == source.identity_key
    assert (
        receipt["draft_revision"] == 1
        and receipt["facts"] == draft["assessment"]["facts"]
    )
    assert exported["operation"] == "create_proposal"
    assert exported["fields"]["Source"] == "EDN OS Email"
    assert exported["fields"]["SubmittedAt"] == source.occurred_at.isoformat()
    assert "native_item_id" not in exported["target"]
    assert "site_id" not in exported["target"]
    assert (
        exported["idempotency_key"]
        == requests.export(job.request_id, 1)["idempotency_key"]
    )


def test_incomplete_job_remains_durable_draft_then_answer_continues(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY.replace("Phone: 0400000000\n", ""))
    first = drafts.ingest(source)
    with pytest.raises(IntakeError, match="Required"):
        drafts.materialise(source.identity_key, 1, requests)
    assert requests.list_requests() == () and drafts.get(source.identity_key) == first
    drafts.answer(source.identity_key, 1, "phone", "0400000000", actor="operator")
    with pytest.raises(IntakeError, match="refresh"):
        drafts.materialise(source.identity_key, 1, requests)
    job = drafts.materialise(source.identity_key, 2, requests)
    assert job.fields["phone"] == "0400000000"
    assert (
        requests.source_provenance(job.request_id)["email_receipt"]["answers"]["phone"][
            "basis"
        ]
        == "operator_confirmed"
    )


def test_changed_answer_invalidates_approval_preserving_corrections_and_history(
    tmp_path,
):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    requests.approve(job.request_id, 1)
    old_export = requests.export(job.request_id, 1)
    drafts.answer(
        source.identity_key, 1, "siteLocation", "Corrected depot", actor="operator"
    )
    changed = drafts.materialise(source.identity_key, 2, requests)
    assert changed.request_id == job.request_id and changed.revision == 2
    assert changed.state == "draft" and changed.fields == job.fields
    assert requests.audit_history(job.request_id)[-1]["decision"] == "source_changed"
    assert requests.source_snapshot(job.request_id)["siteLocation"] == "Corrected depot"
    with pytest.raises(IntakeError):
        requests.approve(job.request_id, 2)
    with (
        pytest.raises(IntakeError),
        requests.authorise_delivery(job.request_id, 1, old_export),
    ):
        pass
    resolved = requests.resolve_source_change(
        job.request_id,
        2,
        decision="apply_source",
        reason="Reviewed synthetic correction",
    )
    assert resolved.fields["siteLocation"] == "Corrected depot"
    requests.approve(job.request_id, resolved.revision)
    assert (
        requests.export(job.request_id, resolved.revision)["idempotency_key"]
        == old_export["idempotency_key"]
    )


@pytest.mark.parametrize(
    "case", ["information", "real", "attachments", "unsafe", "date"]
)
def test_non_jobs_live_sources_and_unpromoted_evidence_cannot_create_jobs(
    tmp_path, case
):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    if case == "information":
        source = replace(source, subject="For your information")
    elif case == "real":
        source = replace(source, source="outlook")
    elif case == "attachments":
        source = replace(
            source, attachments=[{"id": "attachment-1", "name": "synthetic.pdf"}]
        )
    elif case == "unsafe":
        source = replace(
            source, body=BODY.replace("Synthetic depot", "Synthetic\u200b depot")
        )
    else:
        source = replace(source, body=BODY + "\nRequested date: next Tuesday")
    drafts.ingest(source)
    with pytest.raises(IntakeError):
        drafts.materialise(source.identity_key, 1, requests)
    assert requests.list_requests() == ()


def test_concurrent_promotion_creates_one_job(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    drafts.ingest(source)
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = list(
            executor.map(
                lambda _: drafts.materialise(source.identity_key, 1, requests), range(3)
            )
        )
    assert len({job.request_id for job in jobs}) == 1
    assert len(requests.list_requests()) == 1


def test_website_contract_remains_strict_and_cannot_forge_email_import(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    receipt = requests.source_provenance(job.request_id)["email_receipt"]
    payload = {
        **job.fields,
        "source": "EDN OS Email",
        "submittedAt": source.occurred_at.isoformat(),
        "contractVersion": "1.0",
        "email_receipt": receipt,
    }
    with pytest.raises(IntakeError, match="website"):
        requests.import_contract(payload, "1", source_identity=identity())
    payload["email_receipt"] = {**receipt, "event_source_key": "0" * 64}
    with pytest.raises(IntakeError, match="email contract"):
        _record_contract(payload)
    assert (
        requests.import_contract(
            contract(), "1", source_identity=identity()
        ).source_type
        == "synthetic_import"
    )


def test_forwarded_copy_is_review_gated_and_cannot_export_duplicate_work(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    forwarded = replace(source, external_id="forwarded-2")
    for item in (source, forwarded):
        drafts.ingest(item)
    one = drafts.materialise(source.identity_key, 1, requests)
    two = drafts.materialise(forwarded.identity_key, 1, requests)
    assert requests.duplicate_candidates(two.request_id) == (one,)
    with pytest.raises(IntakeError, match="duplicate"):
        requests.approve(two.request_id, 1)
    requests.resolve_duplicate(
        two.request_id,
        one.request_id,
        1,
        decision="same_work",
        reason="Verified synthetic forwarded copy",
    )
    canonical = requests.get(one.request_id)
    requests.approve(canonical.request_id, canonical.revision)
    assert (
        requests.export(canonical.request_id, canonical.revision)["operation"]
        == "create_proposal"
    )
    with pytest.raises(IntakeError, match="Linked"):
        requests.approve(two.request_id, requests.get(two.request_id).revision)


def test_linked_website_record_takes_existing_target_precedence(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY)
    drafts.ingest(source)
    mail = drafts.materialise(source.identity_key, 1, requests)
    manual = requests.create(mail.fields, submission_id=str(uuid4()))
    web = requests.import_contract(
        contract(**mail.fields), "1", source_identity=identity()
    )
    requests.resolve_duplicate(
        mail.request_id,
        manual.request_id,
        1,
        decision="same_work",
        reason="Same synthetic work",
    )
    requests.resolve_duplicate(
        web.request_id,
        manual.request_id,
        1,
        decision="same_work",
        reason="Website already contains this work",
    )
    canonical = requests.get(manual.request_id)
    requests.approve(canonical.request_id, canonical.revision)
    payload = requests.export(canonical.request_id, canonical.revision)
    assert payload["operation"] == "reference_existing"
    assert payload["target"]["native_item_id"] == "1"
