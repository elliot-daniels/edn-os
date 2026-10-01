# IC-008 Intelligence Retrieval & Context Alpha

## Outcome

IC-008 introduces the smallest source-neutral layer that can answer from more
than one authorised EDN information source without replacing Memory, FTS5,
grounded answers, or the deterministic knowledge graph.

```text
question + principal + purpose + domain + classification
                         |
              capability and policy checks
                         |
          authorised source adapters only
                /                     \
       Email Retrieval          Knowledge Graph
                \                     /
             bounded evidence context
                         |
       FACT / INFERENCE / RECOMMENDATION / UNKNOWN
                         |
       provenance + explicit global-knowledge boundary
```

## Reuse decisions

- `RetrievalEngine` remains the email FTS5/ranking implementation and is wrapped
  by `EmailRetrievalAdapter`.
- `KnowledgeGraphStore` remains the entity and relationship store and is wrapped
  by `KnowledgeGraphAdapter`; its facts resolve to supporting email source keys.
- Core `PrincipalContext`, `Purpose`, `SecurityDomain`, `Classification`,
  `EvidenceRef`, Capability Registry, and Permission Evaluator are authoritative.
- The current Ask EDN surface remains operational. IC-008 is an application
  service beneath a later conversational UI increment, not a replacement UI.
- Persistent jobs are not used for an interactive read. They remain authoritative
  for connector discovery, sync, and ingestion work.

## Contracts and security sequence

`IntelligenceRequest` carries the complete authority context. `ContextAssembler`
resolves each adapter capability and evaluates its permission before invoking the
adapter. Missing, ambiguous, degraded, or prohibited decisions fail closed. It
then rejects evidence whose domain or classification differs from the request.
Limits apply per source and to the combined context.

`ContextEvidence` contains a bounded excerpt plus one or more durable Core
`EvidenceRef` values. The source adapter owns mapping from existing record IDs to
universal provenance. No response statement is itself persisted as a source fact.

## Response semantics

- **FACT** requires one or more private evidence IDs and cannot cite global
  knowledge.
- **INFERENCE** remains explicitly labelled and is never silently stored as fact.
- **RECOMMENDATION** may cite private evidence and separately identified global
  knowledge.
- **UNKNOWN** carries no source claims and makes insufficient evidence explicit.

`GlobalKnowledge` is structurally separate from `ContextEvidence`. It has no
`EvidenceRef` and cannot satisfy the provenance requirement for a private fact.

## Session model

The Alpha session store retains only the session's principal, purpose, domain,
classification, and bounded evidence IDs. A follow-up must match all four
authority dimensions. A domain, purpose, classification, or principal change
requires a fresh context build and authorisation. The in-memory implementation is
deliberate for this increment; durable encrypted session storage is a later need.

## Local Files and Microsoft 365 assessment

IC-007 Local Files discovery is metadata-only. Its catalogue can explain what is
available or missing, but discovered filenames and metadata are not treated as
substantive document evidence and no content is ingested by IC-008.

There is no production Outlook/calendar Core read adapter yet. Historical email
Memory plus its derived knowledge graph provide the first safe real multi-source
demonstration. A read-only calendar connector is the highest-value next source
because weekly prioritisation needs current commitments and deadlines. It must
use the Connector SDK, narrow delegated permissions, explicit EDN scope, and
separate live approval.

SharePoint discovery/provisioning artefacts are not a general query backend and
are not repurposed here. A future SharePoint read adapter must expose approved
records through the same source-neutral contract.

## Alpha demonstration

The question “What are the most important things I should be thinking about this
week for EDN Systems, and why?” can be run against the read-only production email
database and graph using an EDN-only context. The deterministic composer returns
up to five evidence-backed facts and one bounded review recommendation. It does
not claim that historical email alone represents the current week; missing live
calendar and current SharePoint context must be shown as capability gaps.

Synthetic tests prove permission-before-retrieval, EDN/PERSONAL/CLIENT isolation,
scope-mismatch rejection, provenance, multi-source composition, explicit global
knowledge, epistemic labels, and follow-up non-expansion.

The sanitized production read-only acceptance run returned 10 bounded evidence
items across Email memory and Knowledge graph in 2.036 seconds. Every item had
provenance, no capability was unavailable, no private content was printed, and no
source mutation was permitted. This is a single-run observation, not a p95
benchmark. The broad weekly question exercises source composition but historical
email and derived graph evidence alone cannot establish current-week completeness.

## Deliberate limits

- no embeddings, vector database, distributed orchestration, or local LLM;
- no content ingestion, cloud provider dispatch, autonomous action, or mutation;
- no inference persistence or promotion to fact;
- no claim that source volume implies business importance; and
- no durable conversation transcript in this Alpha increment.

## Exact next increment

Build a controlled read-only calendar adapter and a thin Streamlit conversation
view over `IntelligenceService`. Demonstrate the weekly question using authorised
historical email/knowledge evidence plus current calendar evidence, with capability
gaps and statement labels visible. Do not add Outlook mail sync unless the calendar
demo proves it is also required.
