"""Synthetic PA-009 protected preflight handoff and replay tests."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edn.core import Classification
from edn.intelligence import (
    DisclosureProjection,
    FreshnessState,
    ModelRequest,
    OpenAIDisclosurePolicy,
    OpenAIPilotConfig,
    OpenAIProvider,
    PilotDispatchError,
    ProjectedEvidence,
    ProtectedPreflightStore,
    ProviderApproval,
    ProviderFailureCode,
)
from edn.intelligence.provider_preflight_store import canonical_json

CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)
EXPIRY = datetime(2099, 1, 1, tzinfo=UTC)


class FakeTransport:
    def __init__(self, response: dict[str, object] | None = None) -> None:
        self.calls = 0
        self.response = response or _response()

    def post(self, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
        del payload
        assert api_key == "synthetic-key"
        self.calls += 1
        return self.response


class OneNetworkFailureTransport(FakeTransport):
    def post(self, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
        del payload, api_key
        self.calls += 1
        raise PilotDispatchError(ProviderFailureCode.NETWORK)


class SequenceTransport(FakeTransport):
    def __init__(self, outcomes: list[dict[str, object] | ProviderFailureCode]) -> None:
        super().__init__()
        self.outcomes = outcomes

    def post(self, payload: dict[str, object], *, api_key: str) -> dict[str, object]:
        del payload
        assert api_key == "synthetic-key"
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ProviderFailureCode):
            raise PilotDispatchError(outcome)
        return outcome


def _response() -> dict[str, object]:
    payload = {
        "statements": [
            {
                "kind": "model_assertion",
                "text": "Synthetic inference for owner review.",
                "disclosed_evidence_ids": ["disclosed-1"],
                "uncertainty": "synthetic test",
                "proposal_only": False,
            }
        ]
    }
    return {
        "id": "response-1",
        "object": "response",
        "status": "completed",
        "model": "gpt-5-mini-2025-08-07",
        "metadata": {
            "edn_request_id": "protected-request-1",
            "edn_provider_id": "openai.api",
            "edn_model": "gpt-5-mini-2025-08-07",
            "edn_policy_id": "openai-daily-brief-pilot-v1",
        },
        "output": [
            {
                "id": "message-1",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "annotations": [],
                        "logprobs": [],
                        "text": json.dumps(payload, separators=(",", ":")),
                    }
                ],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }


def _request(*, excerpt: str = "Synthetic metadata only") -> ModelRequest:
    item = ProjectedEvidence(
        "disclosed-1",
        "Inbox",
        "Synthetic metadata",
        excerpt,
        FreshnessState.CURRENT,
        "synthetic-digest",
        datetime(2026, 8, 14, tzinfo=UTC),
        "inbox.metadata",
        True,
    )
    return ModelRequest(
        "protected-request-1",
        "daily-intelligence",
        "owner",
        "EDN",
        ("disclosed-1",),
        DisclosureProjection("protected-request-1", (item,), 42),
        CLASSIFICATION,
        "model.summarize",
        5,
        synthetic_fixture=False,
    )


def _provider(
    root: Path,
    transport: FakeTransport,
    *,
    enabled: bool = True,
    model: str = "gpt-5-mini-2025-08-07",
    policy_id: str = "openai-daily-brief-pilot-v1",
) -> OpenAIProvider:
    return OpenAIProvider(
        config=OpenAIPilotConfig(enabled=enabled, model=model, policy_id=policy_id),
        policy=OpenAIDisclosurePolicy(
            policy_id,
            "owner-approval",
            CLASSIFICATION,
            frozenset({"EDN"}),
            frozenset({"inbox.metadata", "local-files.metadata"}),
            True,
        ),
        transport=transport,
        environment={"EDN_OPENAI_API_KEY": "synthetic-key"},
        preflight_store=ProtectedPreflightStore(root),
    )


def _persist(
    root: Path, transport: FakeTransport | None = None
) -> tuple[OpenAIProvider, object]:
    provider = _provider(root, transport or FakeTransport())
    preflight = provider.protected_preflight(_request(), expires_at=EXPIRY)
    return provider, preflight


def _active(root: Path) -> Path:
    files = list(root.glob("*.json"))
    assert len(files) == 1
    return files[0]


def _mutate(root: Path, mutation: object) -> None:
    path = _active(root)
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    assert callable(mutation)
    mutation(value)
    path.write_bytes(canonical_json(value))
    path.chmod(0o600)


def test_projection_survives_process_boundary_and_dispatches_once(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    preflight_transport = FakeTransport()
    first, preflight = _persist(root, preflight_transport)
    assert preflight_transport.calls == 0
    assert first.preflight_store is not None
    reloaded = first.preflight_store.load(_request().request_id).request
    assert reloaded.request_id == _request().request_id
    assert reloaded.purpose == _request().purpose
    assert reloaded.projection == _request().projection
    stored = _active(root)
    assert oct(root.stat().st_mode & 0o777) == "0o700"
    assert oct(stored.stat().st_mode & 0o777) == "0o600"
    stored_text = stored.read_text()
    assert "synthetic-key" not in stored_text
    assert '"principal_id"' not in stored_text
    assert '"capability"' not in stored_text

    dispatch_transport = FakeTransport()
    second = _provider(root, dispatch_transport)
    approval = second.approve_protected(
        request_id=_request().request_id,
        preflight_hash=preflight.preflight_hash,  # type: ignore[attr-defined]
        expires_at=EXPIRY,
    )
    response = second.generate_protected(approval)

    assert response.request_id == _request().request_id
    assert dispatch_transport.calls == 1
    assert not ProtectedPreflightStore(root).exists(_request().request_id)
    with pytest.raises(PilotDispatchError) as replay:
        second.generate_protected(approval)
    assert replay.value.code is ProviderFailureCode.INVALID_AUTHORITY
    assert dispatch_transport.calls == 1


@pytest.mark.parametrize(
    "change",
    (
        lambda value: value["request"].__setitem__("request_id", "changed"),
        lambda value: value.__setitem__("model", "changed-model"),
        lambda value: value.__setitem__("disclosure_policy", "changed-policy"),
        lambda value: value["request"]["projection"]["items"][0].__setitem__(
            "field_category", "local-files.metadata"
        ),
        lambda value: value.__setitem__("evidence_count", 2),
        lambda value: value["request"]["projection"]["items"][0].__setitem__(
            "excerpt", "Changed metadata value"
        ),
    ),
    ids=("request", "model", "policy", "category", "count", "value"),
)
def test_changed_envelope_invalidates_owner_hash(
    tmp_path: Path, change: object
) -> None:
    root = tmp_path / "protected"
    _, preflight = _persist(root)
    _mutate(root, change)
    transport = FakeTransport()
    provider = _provider(root, transport)

    with pytest.raises(PilotDispatchError) as exc:
        provider.approve_protected(
            request_id=_request().request_id,
            preflight_hash=preflight.preflight_hash,  # type: ignore[attr-defined]
            expires_at=EXPIRY,
        )
    assert exc.value.code is ProviderFailureCode.INVALID_AUTHORITY
    assert transport.calls == 0


def test_provider_configuration_model_and_policy_changes_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    _, preflight = _persist(root)
    for model, policy in (
        ("changed-model", "openai-daily-brief-pilot-v1"),
        ("gpt-5-mini-2025-08-07", "changed-policy"),
    ):
        transport = FakeTransport()
        provider = _provider(root, transport, model=model, policy_id=policy)
        with pytest.raises(PilotDispatchError):
            provider.approve_protected(
                request_id=_request().request_id,
                preflight_hash=preflight.preflight_hash,  # type: ignore[attr-defined]
                expires_at=EXPIRY,
            )
        assert transport.calls == 0


def test_expiry_unsafe_permissions_and_missing_projection_block(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    provider = _provider(root, FakeTransport())
    old_created = datetime(2020, 1, 1, tzinfo=UTC)
    expired = provider.protected_preflight(
        _request(), expires_at=old_created + timedelta(minutes=5), now=old_created
    )
    with pytest.raises(PilotDispatchError):
        provider.approve_protected(
            request_id=_request().request_id,
            preflight_hash=expired.preflight_hash,
            expires_at=old_created + timedelta(minutes=5),
        )
    assert not ProtectedPreflightStore(root).exists(_request().request_id)

    _, current = _persist(root)
    _active(root).chmod(0o644)
    with pytest.raises(PilotDispatchError):
        provider.approve_protected(
            request_id=_request().request_id,
            preflight_hash=current.preflight_hash,  # type: ignore[attr-defined]
            expires_at=EXPIRY,
        )
    os.chmod(_active(root), 0o600)
    root.chmod(0o755)
    with pytest.raises(PilotDispatchError):
        provider.approve_protected(
            request_id=_request().request_id,
            preflight_hash=current.preflight_hash,  # type: ignore[attr-defined]
            expires_at=EXPIRY,
        )
    root.chmod(0o700)
    ProtectedPreflightStore(root).cancel(_request().request_id)
    with pytest.raises(PilotDispatchError):
        provider.approve_protected(
            request_id=_request().request_id,
            preflight_hash=current.preflight_hash,  # type: ignore[attr-defined]
            expires_at=EXPIRY,
        )


def test_prohibited_content_and_kill_switch_never_persist_or_dispatch(
    tmp_path: Path,
) -> None:
    for request, enabled, code in (
        (_request(excerpt="email body: prohibited"), True, "prohibited_content"),
        (_request(), False, "provider_disabled"),
    ):
        root = tmp_path / code
        transport = FakeTransport()
        provider = _provider(root, transport, enabled=enabled)
        preflight = provider.protected_preflight(request, expires_at=EXPIRY)
        assert not preflight.dispatch_permitted
        assert preflight.refusal_reason == code
        assert transport.calls == 0
        assert not root.exists() or not tuple(root.iterdir())


def test_terminal_failure_destroys_envelope_and_preserves_fallback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    _, preflight = _persist(root)
    transport = FakeTransport(
        {
            "id": "bad",
            "model": "gpt-5-mini-2025-08-07",
            "metadata": {
                "edn_request_id": "protected-request-1",
                "edn_provider_id": "openai.api",
            },
            "output": [],
        }
    )
    provider = _provider(root, transport)
    approval = ProviderApproval(
        preflight.preflight_hash,  # type: ignore[attr-defined]
        _request().request_id,
        "openai.api",
        "gpt-5-mini-2025-08-07",
        "openai-daily-brief-pilot-v1",
        ("inbox.metadata",),
        EXPIRY,
    )
    with pytest.raises(PilotDispatchError) as exc:
        provider.generate_protected(approval)
    assert exc.value.code is ProviderFailureCode.INVALID_RESPONSE
    assert transport.calls == 1
    assert not ProtectedPreflightStore(root).exists(_request().request_id)
    record = provider.audit.records[-1]  # type: ignore[attr-defined]
    assert record.dispatch_status == "refused"
    assert record.transport_attempted is True
    assert record.retryable is False
    assert record.attempt_number == 1


def test_only_one_retryable_failure_can_restore_across_processes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    _, preflight = _persist(root)
    failure_transport = OneNetworkFailureTransport()
    first = _provider(root, failure_transport)
    approval = first.approve_protected(
        request_id=_request().request_id,
        preflight_hash=preflight.preflight_hash,  # type: ignore[attr-defined]
        expires_at=EXPIRY,
    )
    with pytest.raises(PilotDispatchError) as failure:
        first.generate_protected(approval)
    assert failure.value.code is ProviderFailureCode.NETWORK
    assert failure_transport.calls == 1
    assert ProtectedPreflightStore(root).exists(_request().request_id)

    success_transport = FakeTransport()
    second = _provider(root, success_transport)
    second_approval = second.approve_protected(
        request_id=_request().request_id,
        preflight_hash=preflight.preflight_hash,  # type: ignore[attr-defined]
        expires_at=EXPIRY,
    )
    second.generate_protected(second_approval)
    assert success_transport.calls == 1
    assert not ProtectedPreflightStore(root).exists(_request().request_id)


def _approved_provider(
    root: Path, transport: FakeTransport
) -> tuple[OpenAIProvider, ProviderApproval]:
    _, preflight = _persist(root)
    provider = _provider(root, transport)
    approval = provider.approve_protected(
        request_id=_request().request_id,
        preflight_hash=preflight.preflight_hash,  # type: ignore[attr-defined]
        expires_at=EXPIRY,
    )
    return provider, approval


def test_initial_success_is_one_transport_and_zero_retries(tmp_path: Path) -> None:
    provider, approval = _approved_provider(tmp_path / "protected", FakeTransport())

    provider.generate_protected(approval)

    transport = provider.transport
    assert isinstance(transport, FakeTransport)
    assert transport.calls == 1
    day = provider.budget.daily[datetime.now(UTC).date()]
    assert day.requests == 1
    assert day.retries == 0
    assert provider.audit.records[-1].attempt_number == 1  # type: ignore[attr-defined]
    assert provider.audit.records[-1].final_outcome == "completed"  # type: ignore[attr-defined]


def test_retryable_initial_failure_then_success_is_exactly_two_transports(
    tmp_path: Path,
) -> None:
    transport = SequenceTransport([ProviderFailureCode.NETWORK, _response()])
    provider, approval = _approved_provider(tmp_path / "protected", transport)

    with pytest.raises(PilotDispatchError) as first:
        provider.generate_protected(approval)
    assert first.value.code is ProviderFailureCode.NETWORK
    provider.generate_protected(approval)

    assert transport.calls == 2
    day = provider.budget.daily[datetime.now(UTC).date()]
    assert (day.requests, day.retries, day.successful_briefs) == (2, 1, 1)
    records = [
        record
        for record in provider.audit.records  # type: ignore[attr-defined]
        if record.attempt_number > 0
    ]
    assert records[0].transport_attempted is True
    assert records[0].failure_reason == "network_failure"
    assert records[0].retryable is True
    assert records[1].retry_admission_decision == "pending"
    assert records[-1].attempt_number == 2
    assert records[-1].retry_admission_decision == "admitted"
    assert records[-1].initial_failure_code == "network_failure"
    assert records[-1].final_outcome == "completed"


def test_retryable_initial_failure_then_failed_retry_falls_back(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    transport = SequenceTransport(
        [ProviderFailureCode.NETWORK, ProviderFailureCode.PROVIDER_UNAVAILABLE]
    )
    provider, approval = _approved_provider(root, transport)

    with pytest.raises(PilotDispatchError):
        provider.generate_protected(approval)
    with pytest.raises(PilotDispatchError) as final:
        provider.generate_protected(approval)

    assert final.value.code is ProviderFailureCode.PROVIDER_UNAVAILABLE
    assert transport.calls == 2
    assert not ProtectedPreflightStore(root).exists(_request().request_id)
    record = provider.audit.records[-1]  # type: ignore[attr-defined]
    assert record.initial_failure_code == "network_failure"
    assert record.failure_reason == "provider_unavailable"
    assert record.final_outcome == "failed"


def test_retry_authority_mismatch_blocks_second_transport(tmp_path: Path) -> None:
    root = tmp_path / "protected"
    transport = SequenceTransport([ProviderFailureCode.NETWORK, _response()])
    provider, approval = _approved_provider(root, transport)
    with pytest.raises(PilotDispatchError):
        provider.generate_protected(approval)

    mismatched = replace(approval, preflight_hash="0" * 64)
    with pytest.raises(PilotDispatchError) as blocked:
        provider.generate_protected(mismatched)

    assert blocked.value.code is ProviderFailureCode.INVALID_AUTHORITY
    assert transport.calls == 1
    assert not ProtectedPreflightStore(root).exists(_request().request_id)


def test_tampered_retry_failure_metadata_blocks_before_transport(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    transport = SequenceTransport([ProviderFailureCode.NETWORK, _response()])
    provider, approval = _approved_provider(root, transport)
    with pytest.raises(PilotDispatchError):
        provider.generate_protected(approval)
    _mutate(root, lambda value: value.__setitem__("initial_failure_code", "changed"))

    with pytest.raises(PilotDispatchError) as blocked:
        provider.approve_protected(
            request_id=approval.request_id,
            preflight_hash=approval.preflight_hash,
            expires_at=approval.expires_at,
        )

    assert blocked.value.code is ProviderFailureCode.INVALID_AUTHORITY
    assert transport.calls == 1


def test_spend_budget_can_block_retry_without_losing_initial_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "protected"
    transport = SequenceTransport([ProviderFailureCode.NETWORK, _response()])
    provider, approval = _approved_provider(root, transport)
    provider.config = replace(provider.config, max_daily_spend_aud=0.004)

    with pytest.raises(PilotDispatchError) as first:
        provider.generate_protected(approval)
    assert first.value.code is ProviderFailureCode.NETWORK
    with pytest.raises(PilotDispatchError) as second:
        provider.generate_protected(approval)

    assert second.value.code is ProviderFailureCode.BUDGET_EXCEEDED
    assert transport.calls == 1
    record = provider.audit.records[-1]  # type: ignore[attr-defined]
    assert record.transport_attempted is False
    assert record.retry_admission_decision == "blocked"
    assert record.initial_failure_code == "network_failure"
    assert record.failure_reason == "budget_exceeded"
    assert not ProtectedPreflightStore(root).exists(_request().request_id)


def test_terminal_retry_consumption_blocks_replay(tmp_path: Path) -> None:
    root = tmp_path / "protected"
    transport = SequenceTransport(
        [ProviderFailureCode.NETWORK, ProviderFailureCode.TIMEOUT]
    )
    provider, approval = _approved_provider(root, transport)
    with pytest.raises(PilotDispatchError):
        provider.generate_protected(approval)
    with pytest.raises(PilotDispatchError):
        provider.generate_protected(approval)
    with pytest.raises(PilotDispatchError) as replay:
        provider.generate_protected(approval)

    assert replay.value.code is ProviderFailureCode.INVALID_AUTHORITY
    assert transport.calls == 2


def test_retry_audit_contains_metadata_only(tmp_path: Path) -> None:
    transport = SequenceTransport([ProviderFailureCode.NETWORK, _response()])
    provider, approval = _approved_provider(tmp_path / "protected", transport)
    with pytest.raises(PilotDispatchError):
        provider.generate_protected(approval)
    provider.generate_protected(approval)

    serialized = json.dumps(
        [record.to_dict() for record in provider.audit.records],  # type: ignore[attr-defined]
        sort_keys=True,
    )
    assert "synthetic-key" not in serialized
    assert "Synthetic metadata only" not in serialized
    assert "structured_output" not in serialized
    assert "statements" not in serialized
