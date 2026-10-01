# Email Admission V2 — local implementation and review

Prepared 17 September 2026. Starting checkpoint: `1795deae824a27a2118eed40100bfad7a7654bb4`,
branch `feature/executive-brief-reliability`. This document and its examples contain
synthetic data only. No second live pilot or SharePoint inspection was performed.

## Retrieval and admission are separate

The existing Graph mail client is unchanged: Inbox metadata, at most 25 messages,
a bounded received-time window and no continuation requests. Its exact projection
remains `id,parentFolderId,subject,from,toRecipients,receivedDateTime,lastModifiedDateTime,importance,isRead,categories,webLink`.
No body, MIME, attachment, conversation identifier or additional mailbox access
was added. V1 category and dedicated-folder modes remain available and unchanged.

V2 is an explicit opt-in connector mode. It requires a typed `EmailAdmissionPolicy`
and permission scope containing `email-admission-v2:<SHA-256>`. The digest binds
the category, domain, classification, freshness limit and exact verified
relationship snapshots including provenance. Existing category-only grants cannot
authorize V2. A changed snapshot requires a matching reviewed policy scope.
Core identifier validation and the deterministic opaque provider-resource mapping
are unchanged. No provider/model decides relevance.

## Deterministic decisions

| Condition | Outcome/reason |
|---|---|
| Missing or malformed required metadata | rejected / `malformed_metadata` |
| One batch contains different metadata for the same message ID | reject every variant / `conflicting_metadata` |
| Identical repeated message ID | first decision retained; later copies rejected / `duplicate_record` |
| Message outside configured folder or received-time window | rejected / `outside_folder_boundary` or `outside_time_boundary` |
| A matching signal/value maps to multiple verified entities | rejected / `ambiguous_relationship`, even with EDN category |
| Exact category `EDN` | admitted / `explicit_edn_category` |
| Exact sender in fresh verified client snapshot | admitted / `verified_client_sender` |
| Exact sender in fresh verified EDN-address snapshot | admitted / `verified_edn_sender` |
| Exact subject marker `[PROJECT:ATLAS-42]` for a verified project code | admitted / `verified_project_reference` |
| No match and any configured relationship source unusable | unavailable / `relationship_evidence_unavailable` plus source reasons |
| No match and all configured sources checked, fresh and complete | rejected / `no_edn_relevance_signal` |

Malformed records do not discard healthy records from the batch. Conflict and
boundary checks take precedence over a positive relevance signal. Multiple
unambiguous positive relationship signals contribute their provenance. Category
admission needs only email provenance; all relationship source coverage is still
reported. Replaying the same batch reproduces the same decisions, and the existing
run store prevents an already-completed synthetic morning run executing again.

Addresses match exactly, preserving local-part case and normalizing domain case.
No wildcard domain, alias, plus-address, fuzzy name, bare code or thread inference
is enabled. Merely receiving a message at an EDN address cannot admit every Inbox
message. Newsletters from an explicitly verified sender can be admitted; unrelated
marketing is rejected when coverage is complete. Unread, high importance and
recency alone do not establish relevance. Subject markers and sender metadata
are relevance signals, not proof of sender authentication or a real deadline.
Admission does not manufacture priority, urgency, recommendations or actions.

## Verified relationship input and source coverage

`VerifiedRelationship` contains a signal, exact match value, canonical entity key
and an existing `EvidenceRef`. `RelationshipSnapshot` declares its source identity,
state, checked time and rows. The host must supply owner-reviewed verified input;
constructing this class is not verification of a business relationship. This
session supplies synthetic manifests only. No live sender/client/project mapping
has been invented or loaded. There is no automatic SharePoint ingestion.

Clients and Projects must be explicitly declared, including unavailable states.
Additional sources, including Actions or verified EDN contacts, use the same
contract. Each source records state, checked time and relationship count. A complete
checked empty snapshot is distinct from unavailable. Unavailable, stale, partial
and malformed snapshots cannot supply positive relationships. Missing or future
check times mean freshness unknown. The default maximum age is one day; expiry
means stale, even if the stored state says retrieved or empty. Partial snapshots
cannot prove a unique match. A healthy independent signal can still admit a
message while the other source's gap remains visible.

Snapshot provenance must match the connector domain and classification. Duplicate
source IDs, missing required coverage declarations, invalid states and invalid
configuration fail closed. Missing relationships never silently prove a message
irrelevant. Zero admitted records adds `no_admissible_evidence`; it does not mean
there is nothing requiring attention. Completeness only describes the approved
snapshot and bounded query, never the entire business or Inbox.

## Actual morning application integration

The Outlook adapter adds the V2 authority to its registry/policy resource scope.
It forwards source coverage and structured decisions through `SourceBatch` and
`SourceCoverage`. Admitted email retains its original provider/source identity
and evidence reference; relationship-based admission adds the exact supporting
relationship evidence. Existing context conflict/domain checks continue to apply.
Rejected/unavailable records appear in the audit, not as cited intelligence.
The JSON briefing records decisions, policy identity, source freshness and counts;
the Markdown renderer includes an admission audit. Live output would therefore
contain message IDs and approved relationship metadata and needs the same protected
storage/retention as the briefing. No raw rejected-message body or subject is
added to the decision audit.

Two saved examples were generated through the real connector, permission
evaluator, registry, `MorningBriefApplication` and run store using a fake bounded
metadata client:

| Synthetic message | Complete fresh manifests | Clients unavailable / Projects stale |
|---|---|---|
| Explicit EDN correspondence | admitted: category | admitted: category |
| Synthetic client response from client@example.com | admitted: verified client | not admitted: relationship unavailable |
| Review [PROJECT:ATLAS-42] | admitted: verified project | not admitted: relationship unavailable |
| Family dinner | rejected: no relevance signal | not admitted: relationship unavailable |
| Unrelated newsletter | rejected: no relevance signal | not admitted: relationship unavailable |

The first example retrieves 5, admits 3 and includes 3; the gap example retrieves
5, admits 1 and includes 1. Both retain citations only for included evidence.
Examples: [complete Markdown](examples/email-admission-v2.md),
[complete JSON](examples/email-admission-v2.json),
[gap Markdown](examples/email-admission-v2-coverage-gap.md),
[gap JSON](examples/email-admission-v2-coverage-gap.json).
These are local synthetic proof, not additional live pilot results.

## Files and responsibilities

| File | Purpose |
|---|---|
| `src/edn/connectors/admission.py` | Source-neutral typed decision, outcome and relationship coverage contracts |
| `src/edn/connectors/microsoft_outlook/admission.py` | Deterministic V2 policy and verified snapshot inputs |
| `src/edn/connectors/microsoft_outlook/models.py` | Opt-in V2 mode and retrieval audit fields |
| `src/edn/connectors/microsoft_outlook/connector.py` | Exact policy scope, per-record admission, duplicate/conflict handling, provenance |
| `src/edn/intelligence/adapters.py` | Existing generic Outlook evidence adapter receives V2 scope/provenance |
| `src/edn/intelligence/morning_sources.py` | Morning source adapter forwards decisions/coverage/provenance |
| `src/edn/intelligence/models.py` | Optional backward-compatible audit/coverage fields |
| `src/edn/intelligence/context.py` | Retain admission metadata through existing context collection |
| `src/edn/intelligence/morning.py` | Render structured admission audit |
| `src/edn/connectors/microsoft_sharepoint/schema_plan.py` | Inert exact candidate metadata request planner; no executor |
| `tests/connectors/microsoft_outlook/test_admission.py` | Signal, source-state, conflict, policy-scope and malformed-input tests |
| `tests/intelligence/test_email_admission_brief.py` | Real application integration, provenance, caps, source gaps, recovery/replay and healthy-batch retention |
| `tests/connectors/microsoft_sharepoint/test_schema_plan.py` | Metadata-only plan and identity/permission fail-closed tests |
| `docs/examples/email-admission-v2*.md/json` | Four generated synthetic demonstration artifacts |
| `docs/EMAIL-ADMISSION-V2.md` | Architecture, outcomes and validation report |
| `docs/SHAREPOINT-SCHEMA-INSPECTION-PROPOSAL.md` | Separate, unexecuted metadata inspection proposal |
| `docs/MORNING-BRIEF-V2-PILOT-PROPOSAL.md` | Separate, unexecuted V2 pilot review boundary |
| `docs/email-admission-v2-validation.json` | Exact failure-ID comparison and validation evidence |

## Validation and limitations

Final automated counts and exact baseline comparison are recorded in
`email-admission-v2-validation.json`. The baseline has 659 tests: 566 passed,
92 pre-existing Windows failures and 1 skipped. POSIX protected-store checks have
not been weakened. The full failure identities, not just the count, are compared.
Ruff, strict configured mypy (using the repository's Linux platform check),
focused tests, relevant suites and whitespace validation are required before commit.

Final result: **721 tests: 628 passed, 92 failed, 1 skipped**. All 62 new cases
pass. The failed-ID set equals the checkpoint's set exactly: zero new failures
and zero missing baseline failures. Relevant Core/Connector/Intelligence/Retrieval
results within that final run are 407 passed, 47 baseline failures and 1 skipped.
Ruff and strict mypy pass (127 source files); `git diff --check` passes.
Core security validation is byte-identical to the checkpoint after newline
normalization, SHA-256
`502474737f99d49e67cb67e49838858228336b328cedf9c68dfa71d1040fd8e4`.

No mailbox benchmark or additional business-data read was performed. Runtime
classification is bounded by 25 messages and the explicitly supplied manifest;
this session does not claim a large-manifest performance benchmark. Freshness
reporting does not add ingestion or prove current Inbox completeness. Existing
email Graph projection and pagination are unchanged. Broad natural-language
project mentions, domains, thread continuity and sender authentication remain
outside V2. A future `conversationId` field would need separate projection review;
it is not needed or proposed for the smallest next pilot.

## Next owner decisions and safety

1. Review V2 and supply/review a fresh minimal verified relationship manifest,
   including its provenance and resulting exact policy digest.
2. Review the V2 pilot proposal separately; earlier category-only authority is
   not reused. Run nothing until a new one-shot approval names the manifest.
3. Review the independent schema inspection proposal and existing permission
   evidence. The known mail/calendar scopes cannot authorize SharePoint metadata.

This session made zero Microsoft authentications, reads or writes; zero
SharePoint, Outlook, Calendar or UWC accesses; zero provider calls, recurring
schedules, consent/permission changes, deployments, merges or PRs. No protected
live pilot artifacts were read or committed. Only repository/local synthetic
work and feature-branch publication are within this session's authority.
