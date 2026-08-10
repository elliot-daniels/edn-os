# Intelligence Core Implementation Roadmap

## Sequencing rule

Build the smallest vertical proof while establishing contracts that every later
connector reuses. Security-domain enforcement precedes multi-source context.

| Stage | Deliverable | Dependency | Visible value | Risk |
|---|---|---|---|---|
| IC-000 | Approve architecture, terminology and boundaries | None | Low, enables safe build | Low |
| IC-001 | Core envelopes, IDs and tenant/domain context types | IC-000 | Low | Medium |
| IC-002 | Capability Registry with existing capability adapters | IC-001 | Medium: system explains what it can/cannot do | Low |
| IC-003 | Permission/Authority evaluator and synthetic isolation suite | IC-001–002 | Medium: trustworthy boundaries | High |
| IC-004 | Connector SDK, manifest validator, scaffold and conformance tests | IC-002–003 | Medium developer leverage | Medium |
| IC-005 | Persistent jobs/checkpoints/audit; manual worker | IC-001–004 | Medium operational reliability | Medium |
| IC-006 | Local Files metadata discovery + approved subset ingestion | IC-003–005 | **High: first self-expansion demo** | Medium |
| IC-007 | Representative Local Files metadata discovery and capability opportunities | IC-001–006 | High: evidence-led capability choice | Medium |
| IC-008 | Source-neutral retrieval, bounded context, response semantics and Alpha sessions; wrap email/graph | IC-001–007 | **High: first governed multi-source answer** | High |
| IC-009 | Controlled Microsoft 365 calendar read adapter and conversation UI | IC-004–005, IC-008 patterns | High: current weekly context | High |
| IC-010 | Daily Intelligence brief | IC-008–009 | **Very high daily value** | Medium |
| IC-011 | Durable session/follow-up reference store | IC-008–010 | High conversational continuity | Medium |
| IC-012 | Draft/action planning with human approval state | IC-003, IC-009–011 | High administrative value | High |
| IC-013 | Controlled action execution framework | IC-012 plus separate action specs | Later high value | Very high |

The roadmap moves current-email wrapping after foundational contracts but before
Microsoft 365, providing a real second adapter surface for SDK validation. Full
background scheduling is deferred; jobs can be launched manually/CLI in Alpha.

## Stage gates

Each stage requires specification, synthetic tests, security review, capability
registration, migration/rollback and human approval. Live connectors additionally
require exact scope, permissions, authentication, protected outputs and retention.

## First implementation task

### IC-001A — Core contracts and synthetic security contexts

Create documentation-backed Python models/protocols only:

- `SecurityDomain`, `PrincipalContext`, `Purpose`, `Classification`;
- `SourceRef`, `UniversalRecordRef`, `EvidenceRef`;
- `CapabilityManifest`, `CapabilityStatus`, `CapabilityDecision`;
- `PermissionRequest`, `PermissionDecision`;
- no database, network, connector or UI implementation yet.

Add validation and synthetic tests proving stable serialization, unknown/fail-
closed states, EDN/PERSONAL separation and configuration-owned terminology.
Then use those types in IC-002 registry without changing current Memory APIs.

## Compounding leverage metrics

Track connector implementation time, bespoke Core changes, standard-test reuse,
manifest/documentation generation coverage and number of policy/record/job
contracts reused. A third connector should require no Intelligence Router branch
and materially fewer new test categories than Local Files.

## Hardware checkpoints

- IC-006 measures file counts, metadata scan rate and storage projections.
- IC-009 measures sync volume/rate limits.
- IC-008 measures bounded context size and retrieval latency; provider cost waits
  for an explicitly approved provider.
- Only then decide on embeddings, local inference hardware or storage upgrades.

## Deferred roadmap

Personal OS, Xero/finance, SMS, Garmin/health, photos/vision, Home Assistant,
voice, multi-user tenant administration and autonomous actions require separate
domain/security specifications after Alpha.
