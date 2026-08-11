"""Synthetic IC-012 internal proposal and draft security tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from tests.intelligence.test_context_alpha import (
    EDN,
    NOW,
    PERSONAL,
    FakeAdapter,
    _assembler,
    _evidence,
    _request,
)

from edn.intelligence import (
    ActionPlanner,
    ActionStatus,
    AssembledContext,
    InMemoryActionProposalStore,
    IntelligenceRequest,
    IntelligenceService,
    SQLiteActionProposalStore,
    proposal_fingerprint,
)


def _draft_response():
    base = _request()
    request = IntelligenceRequest(
        "Draft it for me",
        base.principal,
        base.purpose,
        base.security_domain,
        base.classification,
    )
    store = InMemoryActionProposalStore()
    service = IntelligenceService(
        _assembler((FakeAdapter("email.retrieve", "email"),)),
        action_planner=ActionPlanner(store),
    )
    return service.answer(request, now=NOW), store


def test_draft_request_creates_evidence_bound_internal_proposal() -> None:
    response, _ = _draft_response()

    assert len(response.proposed_actions) == 1
    proposal = response.proposed_actions[0]
    assert proposal.status is ActionStatus.AWAITING_REVIEW
    assert proposal.draft_text is not None
    assert proposal.source_evidence_ids == ("context:email-0",)
    assert proposal.domain_id == EDN.domain_id
    assert proposal.target_capability == "email.send"
    assert proposal.required_permission == "email.send.execute"
    assert "owner execution approval" in proposal.required_approval
    assert response.statements[-1].text.endswith("Nothing was executed or sent.")


def test_personal_evidence_cannot_drive_edn_proposal() -> None:
    request = _request(EDN)
    personal = _evidence(
        _request(PERSONAL), "email.retrieve", "personal", "Email memory"
    )
    context = AssembledContext(request, (personal,), ())

    with pytest.raises(PermissionError, match="exceeds"):
        ActionPlanner(InMemoryActionProposalStore()).plan(
            context, now=NOW, include_draft=True
        )


def test_exact_hash_and_current_evidence_bind_human_approval() -> None:
    response, store = _draft_response()
    proposal = response.proposed_actions[0]

    with pytest.raises(PermissionError, match="exact proposal"):
        store.review(
            proposal.proposal_id,
            status=ActionStatus.APPROVED_FOR_EXECUTION,
            proposal_hash="changed",
            human_review_ref="owner-review-1",
            now=NOW,
            current_evidence_ids=proposal.source_evidence_ids,
        )
    with pytest.raises(PermissionError, match="no longer authorised"):
        store.review(
            proposal.proposal_id,
            status=ActionStatus.APPROVED_FOR_EXECUTION,
            proposal_hash=proposal.proposal_hash,
            human_review_ref="owner-review-1",
            now=NOW,
            current_evidence_ids=(),
        )

    approved = store.review(
        proposal.proposal_id,
        status=ActionStatus.APPROVED_FOR_EXECUTION,
        proposal_hash=proposal.proposal_hash,
        human_review_ref="owner-review-1",
        now=NOW,
        current_evidence_ids=proposal.source_evidence_ids,
    )
    assert approved.status is ActionStatus.APPROVED_FOR_EXECUTION
    assert approved.human_review_ref == "owner-review-1"


def test_stale_proposal_fails_closed_and_execution_is_impossible() -> None:
    response, store = _draft_response()
    proposal = response.proposed_actions[0]

    with pytest.raises(PermissionError, match="stale"):
        store.review(
            proposal.proposal_id,
            status=ActionStatus.APPROVED_FOR_EXECUTION,
            proposal_hash=proposal.proposal_hash,
            human_review_ref="owner-review-1",
            now=proposal.expires_at + timedelta(seconds=1),  # type: ignore[operator]
            current_evidence_ids=proposal.source_evidence_ids,
        )
    with pytest.raises(PermissionError, match="not implemented"):
        store.review(
            proposal.proposal_id,
            status=ActionStatus.EXECUTED,
            proposal_hash=proposal.proposal_hash,
            human_review_ref="owner-review-1",
            now=NOW,
            current_evidence_ids=proposal.source_evidence_ids,
        )
    assert not hasattr(ActionPlanner(store), "execute")


def test_modified_proposal_supersedes_and_requires_new_approval() -> None:
    response, store = _draft_response()
    proposal = response.proposed_actions[0]
    replacement = replace(
        proposal,
        proposal_id="proposal-revised",
        rationale="Owner-edited rationale.",
        status=ActionStatus.PROPOSED,
        proposal_hash="",
        human_review_ref=None,
    )
    replacement = replace(replacement, proposal_hash=proposal_fingerprint(replacement))

    store.revise(
        proposal.proposal_id,
        replacement,
        proposal_hash=proposal.proposal_hash,
        human_review_ref="owner-edit-1",
    )

    assert store.get(proposal.proposal_id).status is ActionStatus.SUPERSEDED  # type: ignore[union-attr]
    assert store.get("proposal-revised").human_review_ref is None  # type: ignore[union-attr]
    assert replacement.proposal_hash != proposal.proposal_hash


def test_sqlite_store_persists_review_state_without_execution(tmp_path) -> None:
    response, _ = _draft_response()
    proposal = response.proposed_actions[0]
    path = tmp_path / "actions.db"
    store = SQLiteActionProposalStore(path)
    store.initialise()
    store.create(proposal)

    restarted = SQLiteActionProposalStore(path)
    loaded = restarted.get(proposal.proposal_id)

    assert loaded == proposal
    rejected = restarted.review(
        proposal.proposal_id,
        status=ActionStatus.REJECTED,
        proposal_hash=proposal.proposal_hash,
        human_review_ref="owner-reject-1",
        now=NOW,
        current_evidence_ids=(),
    )
    assert rejected.status is ActionStatus.REJECTED


def test_service_lists_and_reviews_only_authorized_principal_proposals() -> None:
    response, store = _draft_response()
    proposal = response.proposed_actions[0]
    base = _request()
    request = IntelligenceRequest(
        "Review internal proposals",
        base.principal,
        base.purpose,
        base.security_domain,
        base.classification,
    )
    service = IntelligenceService(
        _assembler((FakeAdapter("email.retrieve", "email"),)),
        action_planner=ActionPlanner(store),
    )

    assert service.proposals_for_review(request) == (proposal,)
    rejected = service.review_proposal(
        proposal.proposal_id,
        status=ActionStatus.REJECTED,
        proposal_hash=proposal.proposal_hash,
        human_review_ref="owner-ui-review",
        now=NOW,
        current_evidence_ids=(),
    )

    assert rejected.status is ActionStatus.REJECTED
    other = replace(
        request,
        principal=replace(request.principal, principal_id="different-owner"),
    )
    assert service.proposals_for_review(other) == ()


def test_sqlite_review_listing_is_durable_and_scope_filtered(tmp_path) -> None:
    response, _ = _draft_response()
    proposal = response.proposed_actions[0]
    store = SQLiteActionProposalStore(tmp_path / "actions.db")
    store.initialise()
    store.create(proposal)

    restarted = SQLiteActionProposalStore(tmp_path / "actions.db")

    assert restarted.list_for_review(
        principal_id=proposal.principal_id,
        tenant_id=proposal.tenant_id,
        domain_id=proposal.domain_id,
    ) == (proposal,)
    assert (
        restarted.list_for_review(
            principal_id=proposal.principal_id,
            tenant_id=proposal.tenant_id,
            domain_id="PERSONAL",
        )
        == ()
    )
