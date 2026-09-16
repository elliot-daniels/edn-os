"""Realistic opaque IDs through policy, connectors and the actual morning host."""

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest
from tests.connectors.microsoft_calendar import test_calendar as calendar
from tests.connectors.microsoft_outlook import test_outlook as outlook

from edn.connectors.microsoft_calendar import CalendarWindow, MicrosoftCalendarConnector
from edn.connectors.microsoft_outlook import MicrosoftOutlookConnector
from edn.core import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    PermissionEvaluator,
    PermissionOutcome,
    PolicyRule,
    PolicySet,
    SourceRef,
)
from edn.core.security import validate_identifier
from edn.intelligence import (
    CalendarEvidenceAdapter,
    IntelligenceRequest,
    OutlookEvidenceAdapter,
)
from edn.intelligence.morning import MorningBriefApplication, MorningSourceConfiguration
from edn.intelligence.morning_sources import CalendarSourceAdapter, OutlookSourceAdapter
from edn.intelligence.operations import DailySchedule

NATIVE = "AQMk" + "aB0_-" * 40 + "+/=%?#雪=="


@pytest.mark.parametrize(
    "native", [NATIVE, NATIVE * 8], ids=["graph-shaped", "long-opaque"]
)
def test_morning_host_preserves_exact_native_ids_and_internal_policy(
    tmp_path, monkeypatch, native
):
    def forbidden(*args, **kwargs):
        pytest.fail("network or authentication attempted")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    calls = []

    class CalendarClient:
        def calendar_view(self, calendar_id, *args, **kwargs):
            assert calendar_id == native
            calls.append("calendar")
            return (calendar._raw_event("event+/="),)

    class MailClient:
        def messages(self, mailbox_id, folder_id, *args, **kwargs):
            assert mailbox_id == native + "mailbox"
            assert folder_id == native + "folder"
            calls.append("mail")
            raw = outlook._message("message+/=")
            raw["parentFolderId"] = folder_id
            raw["receivedDateTime"] = calendar.NOW.isoformat()
            return (raw,)

    cal = MicrosoftCalendarConnector(
        replace(calendar._config(), calendar_id=native), CalendarClient()
    )
    mail = MicrosoftOutlookConnector(
        replace(
            outlook._config(),
            mailbox_id=native + "mailbox",
            folder_ids=(native + "folder",),
            security_domain=calendar.EDN,
            classification=calendar.CLASSIFICATION,
        ),
        MailClient(),
    )
    sources = (
        CalendarSourceAdapter(cal, CalendarWindow.THIS_WEEK),
        OutlookSourceAdapter(mail),
    )
    assert CalendarEvidenceAdapter(cal).resource_scope == sources[0].resource_scope
    assert OutlookEvidenceAdapter(mail).resource_scope == sources[1].resource_scope
    registry = CapabilityRegistry()
    rules = []
    for source, connector in zip(sources, (cal, mail), strict=True):
        for value in (*source.resource_scope, source.source_instance_id):
            validate_identifier(value, "internal")
            assert native not in value
        manifest = next(
            m
            for m in connector.manifest.capabilities
            if m.capability_id == source.capability_id
        )
        registry.register(
            manifest,
            CapabilityRuntimeState(CapabilityStatus.READY, AuthenticationStatus.VALID),
        )
        rules.append(
            PolicyRule(
                source.capability_id,
                PermissionOutcome.ALLOWED_WITHIN_SCOPE,
                "Offline exact mapped authority",
                capability_ids=frozenset({source.capability_id}),
                resource_scopes=frozenset(source.resource_scope),
            )
        )
    request = calendar._request(cal)
    app = MorningBriefApplication(
        sources=MorningSourceConfiguration(sources, 25, 50, "Australia/Adelaide"),
        registry=registry,
        policy=PermissionEvaluator(PolicySet("offline", "1", tuple(rules))),
        request=IntelligenceRequest(
            "Morning",
            request.principal,
            request.purpose,
            calendar.EDN,
            calendar.CLASSIFICATION,
        ),
        state_directory=tmp_path,
        schedule=DailySchedule(
            timezone="Australia/Adelaide", next_expected_run=calendar.NOW
        ),
    )
    run = app.tick(now=calendar.NOW)
    assert sorted(calls) == ["calendar", "mail"]
    artifact = json.loads(Path(run.result_ref).read_text())
    assert len(artifact["evidence"]) == 2
    refs = [item["provenance"][0]["record"]["source"] for item in artifact["evidence"]]
    assert {ref["provider_resource_id"] for ref in refs} == {native, native + "folder"}
    for ref in refs:
        assert (
            SourceRef.from_dict(
                json.loads(SourceRef(**ref).to_json())
            ).provider_resource_id
            == ref["provider_resource_id"]
        )
        validate_identifier(ref["source_id"], "source")
        validate_identifier(ref["source_instance_id"], "instance")
    # A fresh application reconstructs identical mapping; duplicate tick does no read.
    assert replace(cal.config).authority_id == cal.config.authority_id
    assert app.tick(now=calendar.NOW) is None
    assert len(calls) == 2


def test_wrong_or_missing_internal_authority_fails_before_client_access():
    connector = MicrosoftCalendarConnector(
        calendar._config(), calendar.FakeGraphClient()
    )
    request = calendar._request(connector)
    for scope in [
        (),
        ("edn-calendar",),
        (replace(connector.config, calendar_id="other").authority_id,),
    ]:
        with pytest.raises(PermissionError):
            decision = replace(
                request.authority,
                request=replace(request.authority.request, resource_scope=scope),
            )
            connector._validate_request(
                replace(request, scope=scope, authority=decision)
            )
    assert connector.client.calls == []


@pytest.mark.parametrize("aliases", [(), ("bad+/=",), ("same", "same")])
def test_invalid_folder_alias_mapping_fails_closed(aliases):
    with pytest.raises(ValueError):
        replace(outlook._config(), authority_folder_ids=aliases)


def test_changing_native_folder_does_not_inherit_alias_authority():
    first = replace(outlook._config(), authority_folder_ids=("inbox",))
    second = replace(first, folder_ids=(NATIVE,))
    assert first.authority_folders != second.authority_folders
    assert first.authority_id == second.authority_id


def test_policy_grants_only_exact_internal_calendar_mapping():
    connector = MicrosoftCalendarConnector(
        calendar._config(), calendar.FakeGraphClient()
    )
    request = calendar._request(connector).authority.request
    policy = PermissionEvaluator(
        PolicySet(
            "mapped",
            "1",
            (
                PolicyRule(
                    "exact",
                    PermissionOutcome.ALLOWED_WITHIN_SCOPE,
                    "Exact configured resource",
                    resource_scopes=frozenset(request.resource_scope),
                ),
            ),
        )
    )
    assert (
        policy.evaluate(request, now=calendar.NOW).outcome
        is PermissionOutcome.ALLOWED_WITHIN_SCOPE
    )
    for identity in [
        "edn-calendar",
        replace(connector.config, calendar_id="other").authority_id,
    ]:
        changed = replace(request, resource_scope=(identity, "window:this-week"))
        assert (
            policy.evaluate(changed, now=calendar.NOW).outcome
            is PermissionOutcome.INDETERMINATE
        )
    with pytest.raises(ValueError):
        replace(request, resource_scope=(NATIVE,))


def test_provenance_mapping_rejects_foreign_event_and_folder():
    connector = MicrosoftCalendarConnector(
        calendar._config(), calendar.FakeGraphClient()
    )
    event = connector._event(calendar._raw_event())
    with pytest.raises(ValueError, match="mapping"):
        connector.evidence_ref(replace(event, calendar_id="other"))
    mail = MicrosoftOutlookConnector(outlook._config(), outlook.FakeOutlookClient())
    message = mail._message(outlook._message())
    with pytest.raises(ValueError, match="mapping"):
        mail.evidence_ref(replace(message, folder_id="other"))


def test_source_reference_old_serialization_remains_compatible():
    source = SourceRef("source", "connector", "instance", "Existing source")
    assert "provider_resource_id" not in source.to_dict()
    assert SourceRef.from_dict(source.to_dict()) == source
    for bad in ["", " ", "x\ny", "x\x00y"]:
        with pytest.raises(ValueError):
            replace(source, provider_resource_id=bad)
