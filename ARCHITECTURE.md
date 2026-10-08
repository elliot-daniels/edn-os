# EDN OS implemented architecture

October technical baseline accepted on 1 October 2026: authoritative `main` merge `c85938c44ef230b5e4574b084d709f263b92adc0`, validated source `a81bda7bfa6674c767aeac607ec281da6fd980c0`. See [baseline record](docs/sprint/OCTOBER-BASELINE.md) and [agent onboarding](docs/sprint/AGENT-ONBOARDING.md). This approves repository development, not deployment or live access.

Inspected implementation: `0b2a0bac1419af32106bf1c17a388f3e9b0cdd5f`, 1 October 2026. This is an implementation inventory, not approval to redesign the system. The [Constitution](docs/CONSTITUTION.md), [module map](docs/MODULE-MAP.md) and module specifications remain design authorities. The earlier [architecture specification](docs/ARCHITECTURE.md) describes Foundation/Memory intent; its proposed schema and layout differ from today's implementation.

## Product and flow

EDN OS captures and retrieves organisational knowledge locally, then presents evidence and reviewable decisions. Runtime stores and source content remain outside Git. Streamlit binds to localhost. SQLite/FTS5 supports historical email search; a separate Operations database supports incoming business activity. AI-derived fields never replace source evidence.

```text
PST-derived MBOX / directory -> memory importer -> SQLite emails + FTS5
                                                   -> retrieval -> grounded Ask EDN
                                                   -> rule-based knowledge graph
Governed Local Files / Outlook / Calendar / SharePoint connectors
  -> policy + scope admission -> bounded context -> brief / internal proposal
Explicit Operations Outlook importer -> separate SQLite Events -> read-only Inbox
Website intake (separate repository) -> SharePoint job requests
  [no job-request-to-Operations adapter yet]
```

## Package ownership

| Package under src/edn | Actual responsibility | Evidence |
|---|---|---|
| foundation | Settings, paths, logging, fingerprint, platform errors/types | foundation/config, paths, logging |
| memory | Canonical EmailRecord, parsing, MBOX/directory import, SQLite email search | memory/models.py, storage.py, cli.py |
| retrieval | Query planning, keyword/reranked retrieval | retrieval/engine.py, query.py, reranker.py |
| knowledge | Local extractive answering and evidence/citation validation | knowledge/answering.py, retrieval.py |
| knowledge_graph | Rule extraction, entity/relationship evidence, incremental persistence | knowledge_graph/persistence.py, pipeline.py |
| core | Security context, identity, capability registry, permissions, policy, references | core/security.py, policy.py, references.py |
| connectors | Source contracts, admission, conformance and bounded adapters | connectors/base.py and source subpackages |
| jobs | Internal worker queue, leases/checkpoints/retry | jobs/storage.py, service.py, worker.py |
| intelligence | Context, sessions, briefs, proposals, temporal validity, guarded provider boundary | intelligence/context.py, session.py, morning.py, actions.py |
| development | Repository review/checkpoints, orchestration and bounded delegation | development/authority.py, delegation.py, review.py |
| work_capture | Synthetic Universal Work Capture contracts/service | work_capture/models.py, service.py |
| operations | Immutable Events, replay-safe Outlook intake, isolated local store | operations/models.py, storage.py, outlook.py, cli.py |
| ui | Streamlit composition of Operations, Memory and Intelligence | ui/app.py, operations.py, runtime.py |

`installer/` contains controlled IMS tooling. `power-platform/` contains source-controlled maker artifacts; see the Work Capture handoff for the exact artifact paths and hash baseline. `config/` contains reviewable examples and frozen manifests, not reusable production authority. `tests/` contains synthetic Python suites and separate IMS Pester files. `poc/` contains PST extractor experiments.

## Dependency and authority boundaries

Foundation must not import feature modules. Keep domain contracts in their owning package. Existing UI and Intelligence adapters compose several feature packages (`ui/app.py`, `intelligence/adapters.py`); the old blanket statement that feature modules never import each other does not describe that composition. OCT-09 requests reconciliation, not a wholesale refactor.

The permission-first Intelligence path validates tenant, principal, purpose, domain and classification before retrieval. Operations is a separate explicit importer/read-only UI path; do not assume all Intelligence security controls automatically wrap EventStore. Operations storage approval and access boundaries require separate verification.

The `jobs` package is an execution queue, not an operational jobs/clients/projects CRM. Operations business links are optional opaque IDs. Knowledge graph entities do not establish authoritative business relationships. No architecture change, live source enablement, external executor or new database migration is authorized by this documentation.

## Further design references

[Intelligence Core](docs/intelligence-core/INTELLIGENCE-CORE-V0.1.md), [context security](docs/intelligence-core/CONTEXT-SECURITY-MODEL.md), [universal record model](docs/intelligence-core/UNIVERSAL-RECORD-MODEL.md), [Operations](docs/OPERATIONS-V1.md), [Work Capture](docs/MODULE-004-WORK.md), [IMS](docs/ims/EDN-IMS-Architecture.md). Historical post-Alpha reviews describe their dated baselines; they do not override later implementation evidence.
