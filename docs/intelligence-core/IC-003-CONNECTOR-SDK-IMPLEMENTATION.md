# IC-003 Connector SDK and Conformance Framework

## Purpose and package

`edn.connectors` is the reusable boundary between Intelligence Core and future source/action adapters. It consumes `edn.core` identities, references, capability manifests, registry state, and composed permission decisions. It contains no connector-specific business policy, credentials, persistence, workers, network access, or real source implementation.

```text
src/edn/connectors/
  models.py       immutable manifests and lifecycle envelopes
  base.py         small optional runtime-checkable protocols
  errors.py       machine-readable, content-safe failures
  conformance.py  reusable validation and registry integration
```

## Lifecycle and protocol hierarchy

`Connector` exposes only a manifest. Optional protocols independently model `discover`, `inspect`, `plan`, `authenticate`, `ingest`, `sync`, `checkpoint`/`resume`, `search`, `act`, and `verify`. A connector implements only meaningful protocols. Its connector-level operation set must equal the union of operations declared by its existing `CapabilityManifest` values. The conformance framework reports both declared-but-missing and implemented-but-undeclared operations.

Unsupported operations raise `UnsupportedOperationError`; they are never silently ignored. Authentication is an optional operation and never implies platform permission or action authority.

## Connector manifest

`ConnectorManifest` has durable connector/provider identity, versions, display metadata, category, existing capability manifests, supported lifecycle operations, configuration-schema reference/version, dependencies, minimum Core version, schema version, and a computed SHA-256 hash. Capabilities must have unique IDs and must name the owning connector. Equivalent manifests sort capabilities, operations, and dependencies before hashing and serialization. Deserialization verifies the supplied hash.

Manifests describe code requirements, not operational readiness. `register_manifest_capabilities` registers their capabilities in the existing `CapabilityRegistry` using caller-supplied runtime states. A normal newly installed connector may therefore register as unavailable until configuration, authentication, permission, health verification, and human approval are complete.

Configuration remains separate. Generic SDK/connector code refers to a versioned configuration schema; EDN paths, tenant IDs, account IDs, and allowed roots belong in tenant configuration outside the manifest and source code. Manifest schema references reject embedded credentials and common secret query parameters.

## Requests and authority

`ConnectorRequest` carries request/correlation IDs, `PrincipalContext`, `Purpose`, `SecurityDomain`, `Classification`, capability, exact operation, bounded scope, and a previously composed `CapabilityUseDecision`. Construction fails unless that decision is explicitly usable and exactly bound to every security-relevant request field. Indeterminate, prohibited, approval-required, stale-scope, or mismatched decisions cannot reach a connector through this boundary.

Connectors do not evaluate business policy. The caller follows:

```text
CapabilityRegistry -> PermissionEvaluator -> CapabilityUseDecision
-> ConnectorRequest -> declared connector protocol
```

`require_supported_operation` additionally confirms that the connector manifest declares the capability and operation. A later execution layer must re-evaluate authority immediately before consequential operations; this SDK does not provide that router.

## Metadata-first discovery and universal records

`ResourceCandidate` contains stable resource identity/type, safe source reference, domain, classification, optional size/time, estimated relevance placeholder, known/indexed state, permission requirements, and warnings. It intentionally has no content field. `DiscoveryResult` and `InspectionResult` can therefore catalogue candidates before ingestion.

`IngestResult` returns content-free `UniversalRecordRef` values and an optional checkpoint; `SearchResult` returns `EvidenceRef` values. Existing source-native payloads remain in their owning adapter/store. The SDK does not create a giant universal payload or replace `EmailRecord`.

## Plan binding

`ConnectorPlan` records connector/version, capability, exact operation/scope, required permissions, proposed mutations, risk, irreversible effects, approval requirement, estimates, plan ID, and a deterministic SHA-256 hash. The hash covers all approval-relevant content. Equivalent plans serialize identically, while a scope or mutation change produces another hash and invalidates any future approval bound to the previous plan.

Planning is a distinct capability. An action connector accepts an already approved plan contract; this task deliberately does not implement approval issuance or execution routing.

## Checkpoint and resume

`Checkpoint` records connector/version, configuration hash, operation, source scope, bounded opaque resume marker, last durable item count, and timezone-aware creation time. It contains no credentials. `require_compatible_checkpoint` rejects connector-version or configuration drift before resume. Persistence and checkpoint storage are deferred.

## Verification and errors

Verification states are `verified`, `verified_with_warnings`, `failed`, and `indeterminate`. Only the first two satisfy `is_verified`; indeterminate is never success.

The error hierarchy distinguishes configuration, authentication, permission, approval, dependency, source availability, unsupported operation, transient failure, invalid checkpoint, incompatible source state, verification failure, and indeterminate safety state. Each error has a stable code, transient flag, optional connector ID, and bounded single-line explanation. Source content and credentials must not be placed in explanations.

## Reusable conformance

`check_connector` validates deterministic manifest reconstruction and operation/protocol alignment. `validate_plan_binding` tests repeatability and scope binding. `require_compatible_checkpoint` covers stale checkpoints. Shared helpers cover operation refusal and deterministic registration. Connector test suites should combine these checks with synthetic operation requests to verify:

- unique IDs, permissions, domains, versions, and hashes;
- metadata-only discovery and stable resource identity;
- plan determinism and scope-sensitive hashes;
- checkpoint serialization and version/configuration compatibility;
- fail-closed authority construction;
- structured safe errors; and
- explicit verification semantics.

IC-003 tests define synthetic Files and Accounting connectors with deliberately different protocol shapes. Both pass the same conformance framework without changes to Core.

## Connector skeleton

```python
class ExampleConnector:
    manifest = ConnectorManifest(
        connector_id="example",
        version="1.0.0",
        capabilities=(existing_capability_manifest,),
        supported_operations=frozenset({"discover"}),
        # display/provider/configuration metadata omitted here
    )

    def discover(self, request: ConnectorRequest) -> DiscoveryResult:
        require_supported_operation(self, request)
        # Return metadata candidates only; do not infer authority.
        return DiscoveryResult(request.request_id, resources=())


def test_conformance() -> None:
    assert check_connector(ExampleConnector()).conforms
```

A real connector should add source-specific synthetic fixtures, operation tests, interruption/resume tests where declared, cross-domain cases, and Plan/Apply/Verify cases for mutations.

## Existing EDN module mapping

- Email Memory adapter: discover and inspect MBOX/PST-derived sources; ingest in bounded batches; checkpoint/resume from durable imported identity; verify counts; search via existing FTS/graph retrieval. Existing models and importer remain wrapped, not rewritten.
- SharePoint discovery adapter: discover, inspect, authenticate, and verify using metadata-only read scope.
- IMS deployment adapter: inspect, plan, authenticate, act, and verify. Existing manifest hash, exact target, protected evidence, explicit GO, and post-apply verification map directly to plan binding and action protocols.

These mappings demonstrate expressiveness only; IC-003 does not create the adapters.

## AI-assisted self-extension path

```text
Missing capability reported by registry
-> catalogue/scaffold considered
-> connector specification and manifest generated
-> code implements selected optional protocols
-> standard conformance and isolation tests
-> human security/code review
-> explicit installation approval
-> capabilities registered as supplied runtime state
-> configuration/authentication/verification
-> policy-controlled readiness
```

No code generation, self-installation, approval, or autonomous activation is implemented. Human review remains authoritative and installed code still does not imply availability.
