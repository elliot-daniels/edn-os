# IC-002 Capability Registry and Permission Policy

## Purpose and boundary

IC-002 adds the pure decision layer between Intelligence Core contracts and future connectors or routing. The registry answers what is installed and operationally available. The policy evaluator answers whether an authenticated principal has platform authority for a particular purpose, domain, classification, capability, operation, and resource scope. Neither component executes work, authenticates, probes services, stores secrets, or persists state.

## Capability lifecycle

`CapabilityRegistry` is an in-memory, bounded collection of immutable `CapabilityManifest` and `CapabilityRuntimeState` snapshots. Registration rejects duplicate durable capability IDs. Manifests retain connector/provider identity, version/hash, operations, permissions, domains, risk, and dependencies. Runtime facts retain explicit status, authentication status, unavailable dependencies, missing permissions, health, verification time, and explanation.

Resolution checks, in order: registration, exact operation, exact security domain, disabled or indeterminate state, authentication, dependencies, external permissions, then supplied runtime status. It returns `CapabilityDecision`, never an unexplained boolean. Only `ready` is usable; degraded and indeterminate fail closed. Registry queries are exact and deterministically sorted by capability ID.

Installed code therefore does not imply readiness. Runtime facts are supplied synthetically in IC-002; later connector health and authentication adapters may create new snapshots but cannot grant platform authority.

## Policy structure

`PolicySet` contains immutable, serializable `PolicyRule` values. Empty selector sets mean the rule does not constrain that dimension. Non-empty selectors match exact values for:

- principal ID or principal kind;
- tenant and security-domain ID;
- classification scheme and level;
- explicit purpose;
- capability and operation; and
- requested resource scope.

Resource-scoped rules require a non-empty request scope wholly contained by the rule. `allowed_within_scope` rules must declare scope. Malformed temporary or scoped rules are rejected when configuration is constructed or deserialized.

## Deterministic precedence

Precedence is intentionally conservative:

1. Any matching explicit prohibition wins, choosing the most specific prohibition only for its explanation.
2. Otherwise, rules with the greatest number of constrained selector dimensions are considered.
3. Equally specific rules must produce the same material decision, scope, expiry, and approval reference; conflict returns `indeterminate`.
4. Identical decisions are resolved by stable rule-ID ordering.
5. No match returns `indeterminate`.

Before rules are considered, the requested domain must be explicitly active in the authenticated `PrincipalContext`. Consequently a broad rule cannot grant PERSONAL access to an EDN-only context, authorize another client, or turn PUBLIC access into access to a more sensitive domain.

## Temporary authority

`temporarily_allowed` requires a timezone-aware expiry and an approval reference. Callers inject a timezone-aware evaluation time. At or after expiry the evaluator returns an indeterminate, non-usable decision; authority is never renewed or inferred. Future approval services may issue policy/configuration facts, but this evaluator does not approve anything.

## Composed decisions and explainability

`evaluate_capability_use` evaluates both registry availability and permission policy and returns `CapabilityUseDecision`. It records the full content-free permission request, capability decision, permission decision, final structured outcome, reason code, explanation, and evaluation time.

An explicit prohibition always blocks use. Otherwise an unready capability remains unavailable even if policy allows it. A ready capability still requires an explicit usable permission decision. Approval-required policy produces an approval-required final outcome with the policy explanation. Only ready capability plus currently allowed permission produces `ready`.

## Serialization and audit boundary

Registry snapshots, policies, rules, and composed decisions use deterministic schema-versioned dictionaries/JSON. Sets are sorted and timestamps normalize to UTC. These values contain identifiers, scopes, status, and provenance—not credentials or source content. IC-002 adds no audit database; future persistence should store these serialized decisions in a separate, migration-controlled operational store without coupling it to email memory.

## Future integration

Future connectors declare manifests and supply observed runtime state. A future Intelligence Router asks the registry for exact operation candidates, constructs a `PermissionRequest`, evaluates policy, and consumes only a composed ready decision. Health checks, authentication, approval evidence, configuration loading, persistence, jobs, and execution remain later modules and must not bypass this decision layer.
