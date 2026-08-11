# Intelligence Core Post-Alpha Architecture Review

Date: 2026-08-11  
Baseline: `f2ea8f9abe82120684cad82e558a5686a0a1c72c`  
Scope: repository-only; no authentication, external access, ingestion, SharePoint
change, or external action occurred.

## Finding

Intelligence Core has reached architectural Alpha, not owner-useful Alpha. Its
governance substrate is strong: immutable security context, capability and
permission checks before retrieval, connector contracts, resumable jobs,
provenance, durable authority-bound references, and non-executing action
proposals exist and are synthetically tested.

The product is still principally a historical-email application with an
Intelligence tab. The next milestone should be **Owner Intelligence Beta**: one
durable local conversation and daily brief using current Outlook mail, Calendar,
approved local documents and existing email/graph evidence, with visible gaps
and reviewable drafts, but no external execution.

## Capability map and genuine workflows

| Area | Actual state | Operational limit |
|---|---|---|
| Historical email | SQLite/FTS5 search, reranking, citations | Works from a manually populated archive; not current sync |
| Email knowledge | Evidence-linked graph | Works when its schema exists; historical mail only |
| Context | Permission-first, source-neutral bounded assembly | UI supplies email, graph and a Calendar gap |
| Calendar | Bounded read-only Graph connector and synthetic tests | IC-009-LIVE remains blocked |
| Local Files | Approved-root discovery/jobs; TXT/MD/JSON/CSV ingestion | Separate CLI; not routed to Intelligence; PDF/DOCX unsupported |
| Daily Intelligence | User-invoked zero-to-ten priorities | Generic retrieval mapping with weak freshness/decision ranking |
| Conversation | Durable SQLite evidence-reference store exists | Default UI/service is in-memory; transcript is Streamlit session state |
| Proposals | Hash-bound internal states and SQLite store; no executor | Default store is in-memory; UI has no approve/reject/edit controls |
| Registry/policy | Fail-closed capability/scope decisions | In-memory and manually composed; no onboarding inventory |
| Connectors/jobs | SDK, conformance, checkpoints, leases, retries, metrics | Only Local Files/Calendar native; worker manual |
| Business OS | SharePoint schema discovery/comparison | No item/content retrieval into Intelligence |
| Personal OS | Domain-neutral contracts and isolation tests | No domain pack, sources, UI or approved cross-domain behavior |
| Global/model | Private/global types are separate | No provider, disclosure projection, retention/cost policy |
| External action | Deliberately absent | Correct: IC-012 approval is not execution authority |

What genuinely works end-to-end today:

1. Search and inspect an existing historical local email database.
2. Ask a retrieval-grounded email question and inspect citations.
3. Retrieve bounded email/graph evidence in Intelligence, see the Calendar gap,
   and build a deterministic user-invoked brief.
4. Ask “What should I do?” or “draft” and create one internal evidence-bound
   proposal that is explicitly not sent or executed.
5. Separately run approved-root Local Files discovery, supported-text ingestion,
   job checkpointing and fingerprint verification.
6. Exercise Calendar only with synthetic Graph clients.

## Major gaps and Jarvis blockers

- Current Outlook, live Calendar, approved documents, SharePoint Business OS
  records, finance, CRM/tasks and Personal OS evidence are inaccessible.
- Retrieval is explainable lexical search plus graph expansion, but lacks robust
  recency planning, semantic matching, cross-source deduplication,
  contradictions, commitment/deadline extraction and relevance evaluation.
- Context limits and source round-robin are safe defaults, not information-value
  optimisation. Daily Intelligence maps each hit to a generic priority and
  cannot establish current completeness.
- Durable session/proposal implementations are not wired to the default UI;
  follow-ups do not model conversational intent; owner review controls are absent.
- Capability state is not persistently discovered or progressively onboarded.
- No scheduler, operational health view, verified backup/restore, retention
  workflow, recovery objective or representative mixed-source p95 benchmark exists.
- No Business OS retrieval exists. Personal OS should remain unbuilt until a
  separate domain pack and authority are approved.
- No global/model provider or private-evidence disclosure policy is approved.

Together these mean the system is not current, cannot sustain a durable useful
conversation, cannot see the owner's authoritative operating records, and needs
manual setup outside the product.

## Security and architecture review

The implementation preserves the important boundaries: policy runs before
retrieval; tenant, principal, purpose, domain and classification bind context;
scope mismatches fail closed; PERSONAL evidence cannot drive EDN proposals;
private/global knowledge remain distinct; session continuation matches exact
authority; changed evidence invalidates references/proposals; approval binds an
exact proposal hash; and no executor exists.

The largest current risk is operational composition drift because the UI creates
an ad hoc registry/policy. Future high risks are parser attack surface, Microsoft
consent breadth, SharePoint domain mapping, private model disclosure, unattended
scheduling and generic execution. Roadmap stop conditions isolate each.

## Value-based prioritisation

Raw file count and bytes remain capacity, scan-cost, retention and parser-risk
inputs. They must not primarily determine capability priority. Rank work by:

1. decision usefulness and the cost of missing information;
2. recurrence and owner workflow frequency;
3. administrative leverage and time saved;
4. freshness requirement and stale-evidence cost;
5. information density and authoritativeness;
6. cross-source corroboration value; and
7. authority friction, reversibility, security risk and implementation effort.

This ranks current mail, Calendar, selected business documents and current Daily
Intelligence ahead of broad low-density filesystem coverage.

## Critical path and roadmap

The critical path to Owner Intelligence Beta is PA-001 durable owner runtime,
PA-003 synthetic current-mail connector, PA-004 progressive onboarding, PA-005
separately approved live source activation, then PA-007 current-evidence Daily
Intelligence and an owner usefulness review. PA-002 document ingestion is
parallel high-value work; PA-006 adds Business OS retrieval; PA-008 adds local
scheduling, observability and recovery.

| ID | Outcome | Authority now |
|---|---|---|
| PA-001 | Durable runtime, health and proposal review UX | Autonomous |
| PA-002 | PDF/DOCX and Local Files retrieval, synthetic only | Autonomous; real roots require owner |
| PA-003 | Current Outlook read adapter, synthetic only | Autonomous; live Graph requires owner |
| PA-004 | Value-based capability onboarding | Autonomous |
| PA-005 | Exact live Calendar/mail/file activation | Owner required |
| PA-006 | Business OS SharePoint read adapter, synthetic only | Autonomous; live content requires owner |
| PA-007 | Genuinely current Daily Intelligence | Autonomous after verified sources; owner reviews usefulness |
| PA-008 | Internal scheduling, observability, backup/recovery | Autonomous development; production installation may require owner |

Global/model intelligence and controlled external execution remain later
separately governed boundaries, not authorised implementation tasks. The
machine-readable roadmap records dependencies, acceptance criteria, authority,
risks and stop conditions.

## Next run

Run PA-001 first and revalidate. If bounded-run policy permits, continue with
PA-002 and PA-003 using synthetic fixtures only. Do not attempt IC-009-LIVE or
PA-005 without separate authority.
