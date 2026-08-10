from datetime import UTC, datetime, timedelta

import pytest

from edn.core import (
    AuthenticationStatus,
    CapabilityManifest,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    CapabilityUseDecision,
    Classification,
    PermissionEvaluator,
    PermissionOutcome,
    PermissionRequest,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    UseDecisionOutcome,
    evaluate_capability_use,
    evaluate_operation_candidates,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def domain(domain_id: str, tenant: str = "tenant-one") -> SecurityDomain:
    return SecurityDomain(domain_id, domain_id, tenant)


def request(
    capability: str = "sharepoint.discover",
    operation: str = "read",
    requested_domain: SecurityDomain | None = None,
    *,
    active_domains: tuple[SecurityDomain, ...] | None = None,
    tenant: str = "tenant-one",
    purpose: str = "retrieve",
    scope: tuple[str, ...] = ("site-one",),
) -> PermissionRequest:
    selected = requested_domain or domain("EDN", tenant)
    active = active_domains if active_domains is not None else (selected,)
    return PermissionRequest(
        "request-1",
        PrincipalContext("user-one", tenant, frozenset(active), True, "employee"),
        Purpose(purpose, purpose),
        capability,
        operation,
        selected,
        Classification(f"{tenant}-scheme", "internal", "Internal"),
        scope,
    )


def manifest(
    capability: str = "sharepoint.discover",
    *,
    operations: frozenset[str] = frozenset({"read"}),
    domains: frozenset[str] = frozenset({"EDN"}),
    version: str = "1.0.0",
    manifest_hash: str | None = None,
) -> CapabilityManifest:
    return CapabilityManifest(
        capability,
        "provider-one",
        "connector-one",
        version,
        operations,
        frozenset({"sites.read"}),
        domains,
        "read",
        manifest_hash=manifest_hash,
    )


def runtime(
    status: CapabilityStatus = CapabilityStatus.READY,
    authentication: AuthenticationStatus = AuthenticationStatus.VALID,
    *,
    dependencies: tuple[str, ...] = (),
    permissions: tuple[str, ...] = (),
) -> CapabilityRuntimeState:
    return CapabilityRuntimeState(
        status,
        authentication,
        dependencies,
        permissions,
        "healthy",
        NOW,
    )


def evaluator(*rules: PolicyRule) -> PermissionEvaluator:
    return PermissionEvaluator(PolicySet("policy-one", "1.0.0", rules))


def allow_rule(**changes: object) -> PolicyRule:
    values: dict[str, object] = {
        "rule_id": "allow-read",
        "outcome": PermissionOutcome.ALLOWED,
        "reason": "Read is allowed.",
        "tenant_ids": frozenset({"tenant-one"}),
        "domain_ids": frozenset({"EDN"}),
        "capability_ids": frozenset({"sharepoint.discover"}),
        "operations": frozenset({"read"}),
    }
    values.update(changes)
    return PolicyRule(**values)  # type: ignore[arg-type]


def test_register_retrieve_list_unregister_and_duplicates() -> None:
    registry = CapabilityRegistry()
    registered = registry.register(manifest(), runtime())
    assert registry.get("sharepoint.discover") == registered
    assert registry.list(status=CapabilityStatus.READY) == (registered,)
    assert registry.list(operation="read") == (registered,)
    with pytest.raises(ValueError):
        registry.register(manifest(), runtime())
    assert registry.unregister("sharepoint.discover") == registered
    assert registry.get("sharepoint.discover") is None


def test_manifest_version_hash_and_runtime_round_trip() -> None:
    digest = "a" * 64
    item = manifest(version="2.1.0", manifest_hash=digest)
    state = runtime()
    assert CapabilityManifest.from_dict(item.to_dict()) == item
    assert CapabilityRuntimeState.from_dict(state.to_dict()) == state
    with pytest.raises(ValueError):
        manifest(manifest_hash="not-a-hash")


@pytest.mark.parametrize(
    ("state", "expected", "reason"),
    [
        (runtime(), CapabilityStatus.READY, "ready"),
        (
            runtime(CapabilityStatus.DISABLED),
            CapabilityStatus.DISABLED,
            "capability_disabled",
        ),
        (
            runtime(CapabilityStatus.DEGRADED),
            CapabilityStatus.DEGRADED,
            "capability_degraded",
        ),
        (
            runtime(authentication=AuthenticationStatus.MISSING),
            CapabilityStatus.AUTHENTICATION_REQUIRED,
            "authentication_required",
        ),
        (
            runtime(dependencies=("network",)),
            CapabilityStatus.UNAVAILABLE,
            "dependency_unavailable",
        ),
    ],
)
def test_registry_availability_reasoning(
    state: CapabilityRuntimeState, expected: CapabilityStatus, reason: str
) -> None:
    registry = CapabilityRegistry()
    registry.register(manifest(), state)
    decision = registry.resolve("sharepoint.discover", "read", domain("EDN"))
    assert decision.status is expected
    assert decision.reason_code == reason


def test_registry_rejects_unsupported_and_unknown_requests() -> None:
    registry = CapabilityRegistry()
    registry.register(manifest(), runtime())
    assert registry.resolve("unknown.capability", "read", domain("EDN")).status is (
        CapabilityStatus.INDETERMINATE
    )
    assert registry.resolve(
        "sharepoint.discover", "delete", domain("EDN")
    ).reason_code == ("operation_not_supported")
    assert (
        registry.resolve("sharepoint.discover", "read", domain("PERSONAL")).reason_code
        == "domain_not_supported"
    )


def test_policy_allowed_prohibited_and_approval_required() -> None:
    read = request()
    apply = request("sharepoint.schema-apply", "execute")
    delete = request("sharepoint.data", "delete")
    policy = evaluator(
        allow_rule(),
        PolicyRule(
            "apply-approval",
            PermissionOutcome.APPROVAL_REQUIRED,
            "Schema apply requires owner approval.",
            tenant_ids=frozenset({"tenant-one"}),
            domain_ids=frozenset({"EDN"}),
            capability_ids=frozenset({"sharepoint.schema-apply"}),
            operations=frozenset({"execute"}),
        ),
        PolicyRule(
            "delete-deny",
            PermissionOutcome.PROHIBITED,
            "SharePoint deletion is prohibited.",
            tenant_ids=frozenset({"tenant-one"}),
            operations=frozenset({"delete"}),
        ),
    )
    assert policy.evaluate(read, now=NOW).outcome is PermissionOutcome.ALLOWED
    approval = policy.evaluate(apply, now=NOW)
    assert approval.outcome is PermissionOutcome.APPROVAL_REQUIRED
    assert "owner approval" in approval.reason
    assert policy.evaluate(delete, now=NOW).outcome is PermissionOutcome.PROHIBITED


def test_temporary_authority_expires_fail_closed() -> None:
    expiry = NOW + timedelta(hours=1)
    rule = allow_rule(
        rule_id="temporary-ingest",
        outcome=PermissionOutcome.TEMPORARILY_ALLOWED,
        reason="Temporary ingestion approval.",
        capability_ids=frozenset({"local-files.ingest"}),
        operations=frozenset({"ingest"}),
        domain_ids=frozenset({"PERSONAL"}),
        expires_at=expiry,
        approval_ref="approval-one",
    )
    item = request(
        "local-files.ingest", "ingest", domain("PERSONAL"), scope=("folder-one",)
    )
    policy = evaluator(rule)
    assert policy.evaluate(item, now=NOW).is_allowed(at=NOW)
    expired = policy.evaluate(item, now=expiry)
    assert expired.outcome is PermissionOutcome.INDETERMINATE
    assert not expired.is_allowed(at=expiry)


def test_no_match_and_equal_specificity_conflict_are_indeterminate() -> None:
    item = request()
    assert (
        evaluator().evaluate(item, now=NOW).outcome is PermissionOutcome.INDETERMINATE
    )
    conflict = evaluator(
        allow_rule(),
        allow_rule(
            rule_id="approval-read",
            outcome=PermissionOutcome.APPROVAL_REQUIRED,
            reason="Approval required.",
        ),
    ).evaluate(item, now=NOW)
    assert conflict.outcome is PermissionOutcome.INDETERMINATE


def test_prohibition_precedes_more_specific_allowance() -> None:
    broad_deny = PolicyRule(
        "deny-delete",
        PermissionOutcome.PROHIBITED,
        "Delete is prohibited.",
        operations=frozenset({"delete"}),
    )
    specific_allow = allow_rule(
        rule_id="allow-specific-delete",
        operations=frozenset({"delete"}),
        capability_ids=frozenset({"sharepoint.data"}),
        principal_ids=frozenset({"user-one"}),
    )
    decision = evaluator(broad_deny, specific_allow).evaluate(
        request("sharepoint.data", "delete"), now=NOW
    )
    assert decision.outcome is PermissionOutcome.PROHIBITED
    assert decision.policy_ref == "deny-delete"


def test_domain_and_client_isolation_precedes_broad_rules() -> None:
    broad = PolicyRule("broad-allow", PermissionOutcome.ALLOWED, "Broad allow.")
    personal = domain("PERSONAL")
    edn_only = request(
        "local-files.discover",
        "read",
        personal,
        active_domains=(domain("EDN"),),
    )
    assert evaluator(broad).evaluate(edn_only, now=NOW).outcome is (
        PermissionOutcome.PROHIBITED
    )
    client_b = domain("CLIENT:b")
    client_request = request(
        requested_domain=client_b, active_domains=(domain("CLIENT:a"),)
    )
    assert evaluator(broad).evaluate(client_request, now=NOW).outcome is (
        PermissionOutcome.PROHIBITED
    )


def test_public_authority_does_not_imply_edn_authority() -> None:
    public_rule = allow_rule(rule_id="public-read", domain_ids=frozenset({"PUBLIC"}))
    assert evaluator(public_rule).evaluate(request(), now=NOW).outcome is (
        PermissionOutcome.INDETERMINATE
    )


def test_composition_requires_capability_and_permission() -> None:
    ready = CapabilityRegistry()
    ready.register(manifest(), runtime())
    prohibited = evaluator(
        allow_rule(
            rule_id="deny-read",
            outcome=PermissionOutcome.PROHIBITED,
            reason="Read prohibited.",
        )
    )
    denied = evaluate_capability_use(ready, prohibited, request(), now=NOW)
    assert denied.outcome is UseDecisionOutcome.PROHIBITED
    assert not denied.is_usable

    unavailable = CapabilityRegistry()
    unavailable.register(manifest(), runtime(CapabilityStatus.UNAVAILABLE))
    blocked = evaluate_capability_use(
        unavailable, evaluator(allow_rule()), request(), now=NOW
    )
    assert blocked.outcome is UseDecisionOutcome.UNAVAILABLE


def test_composed_approval_is_explainable_and_serializable() -> None:
    registry = CapabilityRegistry()
    registry.register(manifest(), runtime())
    approval = allow_rule(
        rule_id="approval-read",
        outcome=PermissionOutcome.APPROVAL_REQUIRED,
        reason="Owner approval is required before reading.",
    )
    decision = evaluate_capability_use(
        registry, evaluator(approval), request(), now=NOW
    )
    assert decision.outcome is UseDecisionOutcome.APPROVAL_REQUIRED
    assert "Owner approval" in decision.explanation
    assert CapabilityUseDecision.from_dict(decision.to_dict()) == decision
    assert (
        decision.to_json()
        == CapabilityUseDecision.from_dict(decision.to_dict()).to_json()
    )


def test_policy_serialization_and_malformed_rules() -> None:
    policies = PolicySet("policy-one", "1.0.0", (allow_rule(),))
    assert PolicySet.from_dict(policies.to_dict()) == policies
    assert policies.to_json() == PolicySet.from_dict(policies.to_dict()).to_json()
    with pytest.raises(ValueError):
        PolicySet("bad-policy", "1.0.0", (allow_rule(), allow_rule()))
    with pytest.raises(ValueError):
        PolicyRule("bad-temporary", PermissionOutcome.TEMPORARILY_ALLOWED, "Invalid")


def test_second_tenant_uses_same_evaluator() -> None:
    second = domain("WORKSPACE:west", "tenant-two")
    item = request(
        "records.search",
        "search",
        second,
        tenant="tenant-two",
        scope=("west-repository",),
    )
    rules = PolicyRule(
        "acme-search",
        PermissionOutcome.ALLOWED_WITHIN_SCOPE,
        "West repository search is allowed.",
        tenant_ids=frozenset({"tenant-two"}),
        domain_ids=frozenset({"WORKSPACE:west"}),
        classification_schemes=frozenset({"tenant-two-scheme"}),
        capability_ids=frozenset({"records.search"}),
        operations=frozenset({"search"}),
        resource_scopes=frozenset({"west-repository"}),
    )
    decision = evaluator(rules).evaluate(item, now=NOW)
    assert decision.outcome is PermissionOutcome.ALLOWED_WITHIN_SCOPE
    assert decision.effective_scope == ("west-repository",)


def test_exact_operation_candidate_discovery_is_bounded_and_sorted() -> None:
    registry = CapabilityRegistry()
    registry.register(manifest("zeta.search"), runtime())
    registry.register(manifest("alpha.search"), runtime())
    registry.register(
        manifest("ignored.draft", operations=frozenset({"draft"})), runtime()
    )
    rules = PolicyRule(
        "allow-search",
        PermissionOutcome.ALLOWED,
        "Search allowed.",
        tenant_ids=frozenset({"tenant-one"}),
        domain_ids=frozenset({"EDN"}),
        operations=frozenset({"read"}),
    )
    item = request()
    decisions = evaluate_operation_candidates(
        registry,
        evaluator(rules),
        item.principal,
        item.purpose,
        item.security_domain,
        item.classification,
        "read",
        resource_scope=item.resource_scope,
        now=NOW,
    )
    assert [decision.request.capability_id for decision in decisions] == [
        "alpha.search",
        "zeta.search",
    ]
    assert all(decision.is_usable for decision in decisions)
