from dataclasses import replace
from datetime import timedelta

import pytest
from tests.connectors.microsoft_outlook.test_outlook import (
    CLASSIFICATION,
    EDN,
    NOW,
    FakeOutlookClient,
    _config,
    _message,
    _request,
)

from edn.connectors.admission import AdmissionOutcome
from edn.connectors.microsoft_outlook import (
    MailScopeMode,
    MailWindow,
    MicrosoftOutlookConnector,
)
from edn.connectors.microsoft_outlook.admission import (
    EmailAdmissionPolicy,
    RelationshipSignal,
    RelationshipSnapshot,
    RelationshipState,
    VerifiedRelationship,
)
from edn.core import EvidenceRef, SourceRef, UniversalRecordRef


def relationship(
    signal=RelationshipSignal.CLIENT_SENDER,
    value="client@example.com",
    entity="client-1",
):
    return VerifiedRelationship(
        signal,
        value,
        entity,
        EvidenceRef(
            "verified-" + entity,
            UniversalRecordRef(
                SourceRef(
                    "synthetic-relationships",
                    "synthetic",
                    "owner-manifest",
                    "Synthetic verified relationship",
                ),
                entity,
                EDN,
                CLASSIFICATION,
                "relationship",
            ),
            locator="Synthetic owner-approved manifest",
        ),
    )


def policy(
    *, clients=RelationshipState.RETRIEVED, projects=RelationshipState.RETRIEVED
):
    return EmailAdmissionPolicy(
        EDN,
        CLASSIFICATION,
        (
            RelationshipSnapshot(
                "clients",
                clients,
                NOW,
                (relationship(),) if clients is not RelationshipState.EMPTY else (),
            ),
            RelationshipSnapshot(
                "projects",
                projects,
                NOW,
                (
                    relationship(
                        RelationshipSignal.PROJECT_REFERENCE, "ATLAS-42", "project-4"
                    ),
                )
                if projects is not RelationshipState.EMPTY
                else (),
            ),
        ),
    )


def raw(sender="stranger@personal.example", subject="Family dinner", categories=()):
    value = _message(categories=categories)
    value["from"]["emailAddress"]["address"] = sender
    value["subject"] = subject
    return value


@pytest.mark.parametrize(
    "message,outcome,reason",
    [
        (raw(categories=("EDN",)), "admitted", "explicit_edn_category"),
        (raw(sender="client@example.com"), "admitted", "verified_client_sender"),
        (
            raw(subject="Review [PROJECT:ATLAS-42]"),
            "admitted",
            "verified_project_reference",
        ),
        (raw(), "rejected", "no_edn_relevance_signal"),
        (
            raw(sender="newsletter@marketing.example"),
            "rejected",
            "no_edn_relevance_signal",
        ),
        (
            raw(sender="client@example.com", subject="Newsletter"),
            "admitted",
            "verified_client_sender",
        ),
        ({**raw(), "isRead": False}, "rejected", "no_edn_relevance_signal"),
        ({**raw(), "importance": "high"}, "rejected", "no_edn_relevance_signal"),
        (raw(sender="client2@example.com"), "rejected", "no_edn_relevance_signal"),
        (raw(subject="[PROJECT:ATLAS-420]"), "rejected", "no_edn_relevance_signal"),
        (
            raw(subject="My personal atlas, ATLAS-42"),
            "rejected",
            "no_edn_relevance_signal",
        ),
        (raw(subject="[PROJECT:atlas-42]"), "rejected", "no_edn_relevance_signal"),
        (raw(sender="Client@example.com"), "rejected", "no_edn_relevance_signal"),
        (raw(sender="client@EXAMPLE.COM"), "admitted", "verified_client_sender"),
    ],
)
def test_deterministic_signal_matrix(message, outcome, reason):
    decision = policy().decide(message, now=NOW)
    assert decision.outcome.value == outcome
    assert decision.reasons == (reason,)
    assert decision == policy().decide(message, now=NOW)


@pytest.mark.parametrize("source", ["clients", "projects"])
@pytest.mark.parametrize(
    "state",
    [
        RelationshipState.UNAVAILABLE,
        RelationshipState.STALE,
        RelationshipState.PARTIAL,
        RelationshipState.MALFORMED,
    ],
)
def test_missing_relationship_is_uncertainty_not_negative_evidence(source, state):
    p = policy(**{source: state})
    decision = p.decide(raw(), now=NOW)
    assert decision.outcome is AdmissionOutcome.UNAVAILABLE
    assert f"relationship_{source}_{state.value}" in decision.reasons
    assert not decision.relationship_evidence
    assert (
        p.decide(raw(categories=("EDN",)), now=NOW).outcome is AdmissionOutcome.ADMITTED
    )
    assert p.coverage(NOW)


def test_checked_empty_sources_and_unknown_or_aged_freshness():
    p = policy(clients=RelationshipState.EMPTY, projects=RelationshipState.EMPTY)
    assert p.decide(raw(), now=NOW).outcome is AdmissionOutcome.REJECTED
    for checked in [None, NOW + timedelta(seconds=1), NOW - timedelta(days=2)]:
        changed = replace(
            p, snapshots=(replace(p.snapshots[0], checked_at=checked), p.snapshots[1])
        )
        assert changed.decide(raw(), now=NOW).outcome is AdmissionOutcome.UNAVAILABLE


@pytest.mark.parametrize("state", list(RelationshipState))
def test_optional_actions_relationship_source_uses_the_same_coverage_contract(state):
    p = policy()
    actions = RelationshipSnapshot(
        "actions",
        state,
        NOW,
        () if state is RelationshipState.EMPTY else (relationship(),),
    )
    p = replace(p, snapshots=(*p.snapshots, actions))
    result = p.decide(raw(), now=NOW)
    if state in {RelationshipState.RETRIEVED, RelationshipState.EMPTY}:
        assert result.outcome is AdmissionOutcome.REJECTED
    else:
        assert result.outcome is AdmissionOutcome.UNAVAILABLE
        assert f"relationship_actions_{state.value}" in result.reasons


def test_authority_stable_on_reconstruction_and_changes_with_relationship_evidence():
    p = policy()
    assert p.authority_id == policy().authority_id
    assert (
        p.authority_id
        == replace(p, snapshots=tuple(reversed(p.snapshots))).authority_id
    )
    changed = replace(p.snapshots[0], checked_at=NOW + timedelta(seconds=1))
    assert (
        p.authority_id != replace(p, snapshots=(changed, p.snapshots[1])).authority_id
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"from": None},
        {"from": {"emailAddress": {"address": "bad"}}},
        {"toRecipients": "not-a-list"},
        {"toRecipients": [{}]},
        {"categories": "EDN"},
        {"categories": [4]},
        {"subject": None},
        {"id": ""},
    ],
)
def test_malformed_metadata_fails_closed_even_with_category(changes):
    decision = policy().decide({**raw(categories=("EDN",)), **changes}, now=NOW)
    assert decision.reasons == ("malformed_metadata",)
    assert decision.outcome is AdmissionOutcome.REJECTED


def test_conflicting_verified_entities_override_category_and_do_not_leak_provenance():
    p = policy()
    conflicting = replace(
        p.snapshots[0], relationships=(relationship(), relationship(entity="client-2"))
    )
    p = replace(p, snapshots=(conflicting, p.snapshots[1]))
    result = p.decide(raw(sender="client@example.com", categories=("EDN",)), now=NOW)
    assert result.reasons == ("ambiguous_relationship",)
    assert not result.relationship_evidence


def test_explicit_edn_sender_requires_verified_manifest_not_just_recipient():
    p = policy()
    p = replace(
        p,
        snapshots=(
            *p.snapshots,
            RelationshipSnapshot(
                "edn-contacts",
                RelationshipState.RETRIEVED,
                NOW,
                (
                    relationship(
                        RelationshipSignal.EDN_SENDER,
                        "engineer@edn.example",
                        "engineer-1",
                    ),
                ),
            ),
        ),
    )
    assert p.decide(raw(sender="engineer@edn.example"), now=NOW).reasons == (
        "verified_edn_sender",
    )
    mail = raw()
    mail["toRecipients"] = [{"emailAddress": {"address": "engineer@edn.example"}}]
    assert p.decide(mail, now=NOW).outcome is AdmissionOutcome.REJECTED


def test_policy_snapshot_is_part_of_permission_scope_and_v1_cannot_activate_v2():
    config = replace(_config(), scope_mode=MailScopeMode.ADMISSION_V2)
    client = FakeOutlookClient()
    with pytest.raises(ValueError):
        MicrosoftOutlookConnector(config, client)
    with pytest.raises(ValueError):
        MicrosoftOutlookConnector(_config(), client, admission_policy=policy())
    connector = MicrosoftOutlookConnector(config, client, admission_policy=policy())
    with pytest.raises(PermissionError):
        connector.search_messages(
            _request(connector), window=MailWindow.LAST_7_DAYS, now=NOW, limit=25
        )
    assert client.calls == 0
    assert (
        policy().authority_id
        != policy(clients=RelationshipState.UNAVAILABLE).authority_id
    )


def test_cross_domain_and_missing_coverage_fail_closed():
    p = policy()
    with pytest.raises(ValueError):
        replace(p, snapshots=(p.snapshots[0],))
    with pytest.raises(ValueError):
        replace(p, snapshots=(p.snapshots[0],) * 2)
    relation = relationship()
    bad = replace(
        relation,
        evidence=replace(
            relation.evidence,
            record=replace(
                relation.evidence.record,
                classification=replace(CLASSIFICATION, level_id="other"),
            ),
        ),
    )
    with pytest.raises(ValueError):
        replace(
            p, snapshots=(replace(p.snapshots[0], relationships=(bad,)), p.snapshots[1])
        )
