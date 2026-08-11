# Intelligence Core Alpha v0.1 Specification

## Outcome

One local interface can answer “What do I need to know today?” using multiple
authorised sources, show evidence and uncertainty, preserve follow-up context,
recommend next steps and prepare a business action for approval. It also proves
connector leverage through approved local-file discovery and selective ingestion.

Alpha is not autonomous and does not claim comprehensive understanding.

IC-008 now supplies the governed retrieval/context spine: source adapters are
invoked only after Capability Registry and permission decisions; responses label
facts, inferences, recommendations, and unknowns; private evidence and global
model knowledge are structurally separate; and follow-ups cannot widen authority.
See `IC-008-INTELLIGENCE-RETRIEVAL-CONTEXT.md`.

IC-009 adds the read-only Calendar Connector SDK implementation, Adelaide-aware
bounded windows, conservative mixed-calendar filtering, calendar evidence adapter,
source-family balancing, structured priorities, and a thin conversational
Streamlit surface. Live authentication remains separately gated by
`IC-009-CALENDAR-LIVE-APPROVAL.md`.

IC-010 adds a deterministic, user-invoked Daily Intelligence brief with zero to
ten evidence-backed priorities, confidence, next actions, explicit missing
information, and visible capability gaps.

IC-011 adds a durable local session-reference store that binds follow-ups to the
original authority context and tombstones references removed by later authorised
retrieval. It persists identifiers and authority metadata, never transcripts.

## Sources

### Existing, retained

- historical email Memory (SQLite/FTS5);
- deterministic email knowledge graph; and
- EDN SharePoint structured metadata/data through separately approved read
  capabilities, not through IMS deployment scripts as a query backend.

### Added in Alpha

- Local Files metadata-first discovery and approved-subset text ingestion;
- live Outlook/email read/sync; and
- calendar read/sync.

Contacts are optional only if Outlook/calendar identity matching cannot be useful
without them. Xero, SMS, Garmin, photos and Home Assistant are excluded.

## User experience

The Streamlit interface evolves rather than being replaced. One conversation
surface presents:

```text
Priority
Reason
Evidence
Recommended next action
Confidence
```

Follow-ups such as “Tell me more about #2” reuse authorised evidence references.
“What do you recommend?” visibly separates fact, inference and recommendation.
“Draft what needs doing” creates an internal draft/action plan only; execution
requires a later authority capability.

## Daily intelligence pipeline

1. Resolve principal, EDN domain, declared goals and current date.
2. Resolve capabilities and policy decisions.
3. Retrieve bounded recent/deadline/change evidence from email, calendar,
   SharePoint and approved files.
4. Deduplicate and rank by urgency, impact, confidence and goal relevance.
5. Produce structured candidates with citations and missing-information flags.
6. Validate citations and domain membership.
7. Persist the session's evidence references and item IDs, not a hidden universal
   prompt transcript.

## First self-expansion demonstration

User: “Find useful files on my computer that aren't indexed.”

1. Registry resolves `discover_local_files`; if unavailable, explain the gap.
2. Policy requests approved roots, exclusions, metadata depth and time window.
3. Connector scans metadata only: path, extension, size, timestamps and optional
   hash under bounded rules. It does not open file contents.
4. Compare source identities/hashes with indexed catalogue.
5. Group candidates by type and estimate count, size, value and ingestion cost.
6. Present ranked categories and exact proposed subset.
7. User approves a subset and content-reading purpose.
8. Create resumable ingestion job, extract supported text locally, register
   records/evidence and verify counts/hashes.
9. Registry records verified ingest/search capability and source scope.
10. A grounded query demonstrates gained knowledge.

This workflow is the principal compounding-leverage acceptance test.

## Alpha components

- local Capability Registry;
- deterministic Permission/Authority foundation;
- Connector SDK and conformance suite;
- universal Source/Record/Evidence envelopes;
- persistent Job records/checkpoints (manual worker is sufficient);
- Local Files connector;
- Microsoft 365 read connector for Outlook/calendar;
- adapters around existing email retrieval/graph/SharePoint discovery;
- context router and structured response envelope;
- session store for evidence references and follow-up intents;
- daily intelligence composer; and
- internal action/draft preparation with approval state.

## Measurable acceptance criteria

### Intelligence

- One answer contains evidence from at least two authorised connector/source
  families and passes citation validation.
- Daily brief returns 0–10 ranked items; every item has reason, evidence,
  confidence and recommended next action.
- Insufficient evidence yields an explicit unknown/gap, not invention.

### Provenance

- 100% of substantive facts and recommendations resolve to at least one Evidence
  record and accessible source locator.
- Derived facts record extractor/provider version and input evidence IDs.

### Permissions and isolation

- Synthetic EDN/PERSONAL overlap tests show zero PERSONAL records, counts,
  excerpts or hints in an EDN-only request across retrieval, graph, session and
  brief paths.
- Cloud provider dispatch is refused for context above its configured ceiling.
- Expired or altered approvals are rejected.

### Capabilities

- Registry explains ready, missing-authentication, missing-permission,
  approval-required and unavailable states with dependencies.
- Stale health verification demotes capability and appears in the explanation.

### Self-expansion

- Metadata-only file discovery scans only approved roots and opens zero file
  contents before ingestion approval.
- It identifies already-indexed candidates deterministically.
- Approved subset ingestion resumes after interruption without duplicates.
- Verification reconciles planned, processed, skipped and failed counts.

### Conversation

- At least three follow-up turns resolve prior item/evidence references without
  widening domains or repeating the original question.
- A domain/purpose change forces reauthorisation and context rebuild.

### Recommendation and action preparation

- UI labels facts, inferences, recommendations and proposed actions separately.
- At least one useful EDN action draft includes source evidence, owner/due-date
  suggestions and approval requirement.
- No external action is executable in Alpha without a separately implemented and
  approved capability.

### Extensibility

- Local Files and Microsoft 365 implement the same connector lifecycle,
  capability registration, policy requests, job/checkpoint and evidence tests.
- A synthetic third connector is scaffolded and passes manifest/contract tests
  without changes to Core orchestration.

### Commercial boundary

- EDN terminology, domains, connector instances, policies, metrics and goals are
  loaded from tenant configuration.
- A synthetic second-business configuration validates without forking Core code
  or exposing EDN records.

### Performance and operations

- Interactive retrieval p95 target: under 2 seconds locally for existing corpus,
  excluding provider latency.
- Job progress/checkpoint persists at least every configured batch.
- Telemetry reports throughput, duration, failures, storage and provenance
  coverage without private content.

## Non-goals

No full Personal OS, finance/health/home/photo connectors, autonomous external
communication, complex workflow designer, production scheduler cluster,
multi-tenant SaaS, vector database mandate, mobile app, voice implementation,
agent swarm or local LLM platform.

## Alpha exit decision

Alpha exits only when the acceptance suite passes using synthetic data plus
separately approved local/live validation. Production-source permissions and
actions remain independently approved; passing Alpha does not grant them.
