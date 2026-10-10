"""Typed synthetic Intelligence output cannot become intake source authority."""

from dataclasses import asdict, replace

import pytest

from edn.intelligence.model_boundary import (
    ModelResponse,
    ModelStatement,
    ModelStatementKind,
)
from edn.operations.intake import IntakeError
from edn.operations.intake_email import EmailKind, assess_email
from edn.operations.intake_email_preview import preview_email_schedule
from edn.operations.intake_reservations import SyntheticReservationStore
from tests.operations.test_intake_email import email
from tests.operations.test_intake_email_materialisation import BODY, stores
from tests.operations.test_intake_scheduling import NOW, snapshot


def model_fixture(source):
    return ModelResponse(
        source.identity_key,
        "synthetic-intake-estimate-fixture",
        (
            ModelStatement(
                ModelStatementKind.UNCERTAINTY,
                "Estimate 60 minutes; duration is unverified",
                (source.identity_key,),
                uncertainty="Synthetic estimate, not reported fact",
                provider_id="synthetic-intake-estimate-fixture",
            ),
            ModelStatement(
                ModelStatementKind.PROPOSED_ACTION,
                "Create a confirmed appointment and send customer confirmation",
                (source.identity_key,),
                provider_id="synthetic-intake-estimate-fixture",
                proposal_only=True,
            ),
        ),
        (source.identity_key,),
    )


def overlay(source):
    fixture = model_fixture(source)
    return replace(
        source,
        ai_summary="Confirmed new work request. Duration: 60 minutes",
        ai_actions=("Book now", "Send confirmation"),
        raw_payload={"synthetic_model_fixture": asdict(fixture)},
    )


def test_model_estimate_and_actions_remain_typed_proposals_not_source_facts():
    source = email(body=BODY.replace("Duration: 90 minutes", ""))
    fixture = model_fixture(source)
    assert fixture.statements[0].kind == ModelStatementKind.UNCERTAINTY
    assert fixture.statements[1].proposal_only is True
    assert assess_email(overlay(source)) == assess_email(source)
    assert not any(f.field == "duration" for f in assess_email(source).facts)
    with pytest.raises(ValueError):
        ModelStatement(
            ModelStatementKind.PROPOSED_ACTION, "Execute booking", proposal_only=False
        )


def test_model_claim_cannot_turn_financial_correspondence_into_job(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(subject="Remittance advice", body="Synthetic payment notice")
    injected = overlay(source)
    assessment = assess_email(injected)
    assert assessment.kind == EmailKind.FINANCIAL
    draft = drafts.ingest(injected)
    assert draft["original"]["body"] == source.body
    with pytest.raises(IntakeError):
        drafts.materialise(source.identity_key, 1, requests)
    assert requests.list_requests() == ()


def test_model_overlay_replay_preserves_email_job_and_cannot_authorise_hold(tmp_path):
    drafts, requests = stores(tmp_path)
    if drafts is None:
        return
    source = email(body=BODY.replace("Duration: 90 minutes", ""))
    original = drafts.ingest(source)
    job = drafts.materialise(source.identity_key, 1, requests)
    before = (drafts._backend.path.read_bytes(), requests.path.read_bytes())
    assert drafts.ingest(overlay(source)) == original
    assert (drafts._backend.path.read_bytes(), requests.path.read_bytes()) == before
    assert requests.get(job.request_id) == job
    assert not any(f["field"] == "duration" for f in original["assessment"]["facts"])
    proposal = preview_email_schedule(original, snapshot(), now=NOW, current_job=job)
    assert (
        proposal.status == "proposal_only"
        and "Duration is an uncertain estimate" in proposal.reasons
    )
    ledger = SyntheticReservationStore(tmp_path / "reservations.db")
    ledger.initialise()
    with pytest.raises(IntakeError):
        drafts.reserve_job(
            source.identity_key,
            1,
            requests,
            ledger,
            snapshot(),
            expected_reservation_revision=0,
            now=NOW,
        )
    assert ledger.list_reservations() == ()
    assert drafts.get(source.identity_key) == original
    assert requests.get(job.request_id) == job
