# Intelligence Core Connector SDK

Status: v0.1 contract design

## Purpose

The SDK makes the next connector cheaper by standardising lifecycle, capability
declaration, security metadata, checkpoints, evidence and tests. Connectors adapt
sources; they do not decide policy, assemble cross-source context, or approve
actions.

## Package boundary

```text
src/edn_core/connectors/
  contracts.py
  models.py
  validation.py
  runtime.py
connectors/<connector_id>/
  connector.py
  manifest.yaml
  fixtures/
  tests/
```

This is a future layout, not authorisation to move existing packages in v0.1.

## Lifecycle contract

```python
class Connector(Protocol):
    manifest: ConnectorManifest

    def discover(self, request: DiscoveryRequest) -> DiscoveryResult: ...
    def inspect(self, source: SourceRef) -> InspectionResult: ...
    def plan(self, request: OperationRequest) -> OperationPlan: ...
    def authenticate(self, request: AuthRequest) -> AuthResult: ...
    def ingest(self, plan: ApprovedPlan, checkpoint: Checkpoint | None) -> BatchResult: ...
    def sync(self, plan: ApprovedPlan, checkpoint: Checkpoint | None) -> BatchResult: ...
    def checkpoint(self) -> Checkpoint: ...
    def resume(self, checkpoint: Checkpoint) -> BatchResult: ...
    def verify(self, operation: OperationRef) -> VerificationResult: ...
    def search(self, query: ConnectorQuery) -> EvidencePage: ...
    def act(self, action: ApprovedAction) -> ActionResult: ...
```

Methods are optional and declared as capabilities. Runtime calls an undeclared
method only as a contract error. Authentication is separated from discovery and
does not imply operation authority.

## Connector manifest

| Field | Meaning |
|---|---|
| `connector_id`, `version` | Stable identity and semantic version |
| `provider` | Source system/vendor, not a secret |
| `capabilities` | Declared method/capability IDs and versions |
| `security_domains` | Allowed domain patterns; never grants access itself |
| `permissions` | External and platform permissions required per operation |
| `authentication_modes` | Interactive, delegated, local path, etc. |
| `data_classes` | Possible classifications/content types |
| `checkpoint_schema` | Versioned resumability contract |
| `record_types` | Source-specific records emitted |
| `action_levels` | Read, draft, write, delete, external side effect |
| `health_check` | Non-mutating verification procedure |
| `limits` | Rate, batch, size and concurrency constraints |

Manifests describe requirements; the Capability Registry records actual status
and grants.

## Progressive ingestion

```text
discover metadata -> catalogue candidates -> estimate value/cost/risk
-> policy evaluation -> user-approved plan -> bounded batches
-> checkpoint -> verify -> index/extract -> register capability health
```

Discovery must support metadata-only operation without reading content wherever
the source permits. Plans list exact scopes, counts/estimates, storage impact,
permissions, classifications, exclusions, checkpoint strategy and rollback.

## Source identity and records

Each connector emits a stable `SourceRef` and source-specific `SourceRecord`.
Identity is `(connector_id, source_instance_id, source_record_key)`. Content
fingerprints supplement identity but do not replace a stable native key.
Connectors must represent deletion, inaccessibility and supersession explicitly.

## Action contract

An action plan contains capability ID, target, exact change, preconditions,
authority decision, idempotency key, expected result, verification, rollback and
expiry. `act()` accepts only an `ApprovedAction`; it must never convert a draft
plan into authority. Delete/share/send operations require distinct capabilities.

## Standard connector test kit

Every connector runs synthetic tests for:

- manifest/schema validation and unique capability IDs;
- undeclared method refusal;
- metadata-only discovery boundaries;
- stable identities and deterministic output;
- incremental batches, checkpoint, interruption and resume;
- duplicate-safe reprocessing;
- permission denial and expired approval;
- secret/content exclusion from logs;
- cross-domain scope rejection;
- dry-run/Plan with zero mutations;
- idempotent action execution and verification;
- partial failure/retry exhaustion; and
- health status registration.

Live fixtures are prohibited from Git. Contract fixtures use reserved domains and
invented IDs.

## Scaffolding experience

Target developer workflow:

```text
scaffold connector -> select capabilities -> generate manifest/contracts/tests
-> implement source adapter -> run standard conformance suite
-> security review -> register unavailable capability
-> approve source instance -> verify -> capability becomes available
```

Generated documentation should derive capability/permission tables from the
manifest to prevent drift.

## Alpha adapters

- Wrap current MBOX importer as an ingest/resume adapter; do not rewrite it.
- Wrap current email FTS/graph retrieval as search capabilities.
- Wrap existing SharePoint discovery and manifest deployment as separate
  discover and controlled-action capabilities.
- Implement Local Files first as a native SDK connector.
- Implement Microsoft 365 live email/calendar only after Local Files validates
  contract ergonomics.

