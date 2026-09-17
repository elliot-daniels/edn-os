"""Synthetic metadata through real connector, policy, registry and morning host."""

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest
from tests.connectors.microsoft_outlook.test_admission import policy, raw
from tests.connectors.microsoft_outlook.test_outlook import (
    CLASSIFICATION,
    EDN,
    NOW,
    _config,
)

from edn.connectors.microsoft_outlook import MailScopeMode, MicrosoftOutlookConnector
from edn.connectors.microsoft_outlook.admission import RelationshipState
from edn.core import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    PermissionEvaluator,
    PermissionOutcome,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
)
from edn.intelligence import IntelligenceRequest
from edn.intelligence.morning import MorningBriefApplication, MorningSourceConfiguration
from edn.intelligence.morning_sources import OutlookSourceAdapter
from edn.intelligence.operations import DailySchedule


class MetadataClient:
    def __init__(self, records):
        self.records = records
        self.calls = []

    def messages(self, mailbox_id, folder_id, start, end, *, limit):
        self.calls.append((mailbox_id, folder_id, start, end, limit))
        return tuple(self.records[:limit])


def build_application(directory, records=None, *, admission=None, grant_v2=True):
    if records is None:
        records = [
            {
                **raw(categories=("EDN",)),
                "id": "category",
                "subject": "Explicit EDN correspondence",
            },
            {
                **raw(sender="client@example.com"),
                "id": "client",
                "subject": "Synthetic client response",
            },
            {**raw(subject="Review [PROJECT:ATLAS-42]"), "id": "project"},
            {**raw(), "id": "personal"},
            {**raw(sender="newsletter@marketing.example"), "id": "newsletter"},
        ]
    client = MetadataClient(records)
    p = admission or policy()
    connector = MicrosoftOutlookConnector(
        replace(_config(), scope_mode=MailScopeMode.ADMISSION_V2),
        client,
        admission_policy=p,
    )
    adapter = OutlookSourceAdapter(connector)
    registry = CapabilityRegistry()
    registry.register(
        next(
            m
            for m in connector.manifest.capabilities
            if m.capability_id == adapter.capability_id
        ),
        CapabilityRuntimeState(CapabilityStatus.READY, AuthenticationStatus.VALID),
    )
    scope = (
        adapter.resource_scope
        if grant_v2
        else tuple(s for s in adapter.resource_scope if s != p.authority_id)
    )
    evaluator = PermissionEvaluator(
        PolicySet(
            "synthetic-v2",
            "1",
            (
                PolicyRule(
                    "bounded",
                    PermissionOutcome.ALLOWED_WITHIN_SCOPE,
                    "Synthetic exact policy and source",
                    resource_scopes=frozenset(scope),
                    capability_ids=frozenset({adapter.capability_id}),
                ),
            ),
        )
    )
    request = IntelligenceRequest(
        "Morning",
        PrincipalContext("owner", "tenant", frozenset({EDN}), True),
        Purpose("synthetic-morning", "Offline validation"),
        EDN,
        CLASSIFICATION,
    )
    app = MorningBriefApplication(
        sources=MorningSourceConfiguration((adapter,), 25, 50, "Australia/Adelaide"),
        registry=registry,
        policy=evaluator,
        request=request,
        state_directory=directory,
        schedule=DailySchedule(timezone="Australia/Adelaide", next_expected_run=NOW),
    )
    return app, client


def result(app):
    run = app.tick(now=NOW)
    return json.loads(Path(run.result_ref).read_text())


def test_real_morning_path_admission_provenance_and_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("Network forbidden")
    )
    app, client = build_application(tmp_path)
    artifact = result(app)
    coverage = artifact["coverage"][0]
    assert len(client.calls) == 1 and client.calls[0][-1] == 25
    assert coverage["pre_filter_count"] == 5
    assert coverage["admitted_count"] == 3 and coverage["selected_count"] == 3
    assert [
        d["record_key"]
        for d in coverage["admission_decisions"]
        if d["outcome"] == "rejected"
    ] == ["personal", "newsletter"]
    assert {s["source_id"] for s in coverage["relationship_sources"]} == {
        "clients",
        "projects",
    }
    evidence = artifact["evidence"]
    assert len(evidence) == 3
    client_item = next(e for e in evidence if e["context_id"].endswith(":client"))
    assert len(client_item["provenance"]) == 2
    assert client_item["provenance"][1]["record"]["source_record_key"] == "client-1"
    ids = {e["context_id"] for e in evidence}
    for section in artifact["brief"]["sections"]:
        for item in section["items"]:
            assert set(item["evidence_ids"]) <= ids
    assert "## Admission audit" in artifact["markdown"]
    assert not app.service.proposals_for_review(app.request)
    again, _ = build_application(tmp_path)
    assert again.tick(now=NOW) is None


def test_no_v2_scope_means_zero_retrieval(tmp_path):
    app, client = build_application(tmp_path, grant_v2=False)
    artifact = result(app)
    assert client.calls == []
    assert artifact["coverage"][0]["status"] == "unavailable"


@pytest.mark.parametrize(
    "changes",
    [
        {"from": {"emailAddress": "invalid"}},
        {"toRecipients": [{"emailAddress": None}]},
        {"categories": None},
    ],
)
def test_malformed_record_does_not_discard_healthy_mail(tmp_path, changes):
    app, _ = build_application(
        tmp_path,
        records=[
            {**raw(categories=("EDN",)), "id": "bad", **changes},
            {**raw(categories=("EDN",)), "id": "healthy"},
        ],
    )
    artifact = result(app)
    coverage = artifact["coverage"][0]
    assert coverage["admitted_count"] == 1
    assert coverage["admission_decisions"][0]["reasons"] == ["malformed_metadata"]
    assert len(artifact["evidence"]) == 1


def test_missing_sources_disclosed_without_discarding_explicit_category(tmp_path):
    app, _ = build_application(
        tmp_path,
        admission=policy(
            clients=RelationshipState.UNAVAILABLE, projects=RelationshipState.STALE
        ),
    )
    artifact = result(app)
    assert len(artifact["evidence"]) == 1
    coverage = artifact["coverage"][0]
    assert "relationship_clients_unavailable" in coverage["reasons"]
    assert "relationship_projects_stale" in coverage["reasons"]
    assert (
        sum(d["outcome"] == "unavailable" for d in coverage["admission_decisions"]) == 4
    )


def test_zero_admitted_is_gap_and_bounded_batch_is_not_total_mailbox(tmp_path):
    records = [{**raw(), "id": str(i)} for i in range(30)]
    app, client = build_application(tmp_path, records)
    artifact = result(app)
    coverage = artifact["coverage"][0]
    assert coverage["pre_filter_count"] == 25 and not artifact["evidence"]
    assert "source_truncated" in coverage["reasons"]
    assert "no_admissible_evidence" in coverage["reasons"]
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "mode",
    ["replay", "conflict", "malformed", "outside-window", "outside-folder", "body"],
)
def test_metadata_boundary_and_replay_audit(tmp_path, mode):
    message = {**raw(categories=("EDN",)), "id": "same"}
    if mode == "replay":
        records = [message, dict(message)]
    elif mode == "conflict":
        records = [message, {**message, "subject": "Conflicting subject"}]
    else:
        changes = {
            "malformed": {"receivedDateTime": "bad"},
            "outside-window": {"receivedDateTime": "2020-01-01T00:00:00Z"},
            "outside-folder": {"parentFolderId": "other"},
            "body": {"body": "prohibited"},
        }
        records = [{**message, **changes[mode]}]
    app, _ = build_application(tmp_path, records)
    artifact = result(app)
    decisions = artifact["coverage"][0]["admission_decisions"]
    assert len(artifact["evidence"]) == (1 if mode == "replay" else 0)
    if mode == "replay":
        assert decisions[1]["reasons"] == ["duplicate_record"]
    if mode == "conflict":
        assert all(d["reasons"] == ["conflicting_metadata"] for d in decisions)
