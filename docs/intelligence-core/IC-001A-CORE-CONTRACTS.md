# IC-001A Core Contracts and Security Contexts

## Purpose

`edn.core` is the dependency-light contract layer for Intelligence Core. It defines immutable values that may cross future connector, capability, policy, job, retrieval, and audit boundaries. It performs no authentication, persistence, network access, UI work, or policy evaluation.

## Package structure

- `security.py`: durable security domains, authenticated principal contexts, purposes, and configurable classifications.
- `references.py`: content-free source, universal-record, and evidence references plus evidence eligibility helpers.
- `capabilities.py`: connector/provider manifests, explicit runtime statuses, and capability decisions.
- `permissions.py`: permission requests and explicit, time-aware permission decisions.

The package is additive. Existing memory, retrieval, knowledge, knowledge-graph, UI, and IMS modules are unchanged.

## Identity rules

A security domain is identified by its exact `domain_id` and tenant association. Labels and owner metadata do not change identity. Scoped domains such as `CLIENT:<stable-id>` are validated but not enumerated in platform code. Source-record identities preserve the source ID and exact source-native record key. Classification identity is its scheme and level; display names and optional ranks are metadata.

Identifiers are validated conservatively and are never silently lowercased or rewritten. Tenant-specific values are supplied by configuration or upstream authenticated context, not built into the platform.

## Fail-closed semantics

`PrincipalContext` represents context already authenticated by another layer. Unauthenticated contexts, missing tenant identity, and empty active-domain sets are invalid. Domain eligibility requires an exact active-domain match and compatible tenant; no hierarchy or implicit PUBLIC/owner access exists.

`is_evidence_eligible`, `filter_eligible_evidence`, and `count_eligible_evidence` must be applied before citations, ranking outputs, and aggregates. A missing context returns no eligible evidence. Retrieved evidence does not carry authority into a later, narrower context.

Capability availability uses explicit states; only `ready` is usable. Permission decisions include `allowed`, `allowed_within_scope`, `approval_required`, `temporarily_allowed`, `prohibited`, and `indeterminate`. Only the explicit allowed outcomes pass `is_allowed`; indeterminate and malformed decisions fail closed. Temporary authority requires an approval reference and timezone-aware expiry.

## Serialization and sensitive data

Every contract has deterministic `to_dict`/`to_json` output and strict `from_dict` reconstruction under schema version `1.0.0`. Sets are emitted in sorted order and timestamps in UTC. Reference contracts carry IDs, classifications, provenance locators, versions, and hashes—not source payloads. Reference URIs reject embedded credentials and common secret query parameters.

## Platform configuration boundary

The contracts contain no EDN-specific tenant, person, email domain, security-domain vocabulary, or classification vocabulary. Synthetic tests instantiate both an EDN-like tenant and a second unrelated business with different domain and classification schemes. Applications may define their own vocabularies while retaining the same validation and serialization behavior.

## Guidance for later modules

Future code should accept these contracts at boundaries instead of unstructured mappings. Authentication supplies `PrincipalContext`; configuration supplies classification and domain vocabularies; the future registry reports `CapabilityStatus`; the future policy engine produces `PermissionDecision`. Callers must re-check evidence eligibility for every request and must never interpret missing or indeterminate state as authority.
