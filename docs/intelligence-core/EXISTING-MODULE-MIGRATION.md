# Existing EDN OS Module Migration Map

## Strategy

Preserve production-tested behaviour. Introduce adapters at boundaries, migrate
consumers, then consider internal refactors only when multiple connectors prove a
shared abstraction. No big-bang database or package rewrite.

| Existing component | Disposition | Intelligence Core role | Migration action |
|---|---|---|---|
| `edn.foundation` config/paths/errors/fingerprint | Keep unchanged initially | Platform utilities below Core | Extend only after two durable consumers; do not turn Foundation into registry/plugin container |
| `EmailRecord` | Keep source-specific | Email payload in universal Record envelope | Add adapter preserving `source_record_key`; do not flatten/delete fields |
| parser and MBOX import | Wrap behind connector interface | Historical email ingest capability | Adapter delegates batches/progress/checkpoints; preserve CLI and duplicate semantics |
| directory importer | Wrap | Multi-source discovery/import job implementation | Translate mailbox summaries to Job progress/results |
| `SQLiteEmailStore` and FTS5 | Keep unchanged | Email repository/search backend | Domain-scoped adapter; retain locking/read-only modes and schema |
| `RetrievalEngine` | Refactor gradually | Evidence-retrieval composition seam | Generalise candidate/evidence types after universal evidence adapter proves parity |
| query normalisation | Keep | Local lexical query provider | Reuse; later allow domain/provider-specific query plans |
| deterministic reranker | Keep/wrap | Explainable ranking provider | Accept universal candidates later; preserve scoring/explanations |
| `RetrievalEvidence` | Migrate behind adapter | Universal Evidence projection | Compatibility type remains until UI/answering migrate |
| `KnowledgeCandidateRetriever` | Keep/wrap | Supplemental email evidence provider | Emit entity explanations and universal evidence refs |
| `knowledge.answering` provider protocol | Refactor | First `ReasoningProvider`/grounding validator | Preserve extractive default; separate provider dispatch from context assembly |
| citation validation | Keep and generalise | Provenance validation | Support namespaced evidence IDs and mixed-source citations |
| deterministic extractor/rules | Keep | Email-specific observation/fact extractor | Register extractor version; do not make patterns Core concepts |
| graph persistence | Migrate incrementally | Domain knowledge projection | Add domain/evidence envelope adapters; avoid rewriting current SQLite graph |
| graph pipeline checkpoint | Keep/wrap | Job checkpoint pattern | Surface as registered extraction job |
| Streamlit Search/Ask/Knowledge | Refactor incrementally | Alpha interface | Add conversation/daily views through application services; no direct Core stores in UI |
| UI read-only database service | Keep | Safe local repository adapter | Preserve friendly busy/unavailable errors |
| SharePoint discovery tooling | Wrap, not merge | Connector discover/inspect/verify capabilities | Registry entries reference script/schema hashes and approval state |
| IMS comparator | Keep as specialist offline tool | Business OS assessment capability | Do not make generic Core inference |
| IMS manifest deployment | Wrap as controlled action | Example Plan→GO→Apply capability | Bind capability to exact site/manifest/approval; never general write permission |
| IMS policy concepts | Extract configuration patterns | Permission/Authority inputs | Reuse unknown-vs-absent, no-clobber, hash, human authority and rollback rules |

## Package evolution

Do not rename `edn` or move current modules during IC-001. Introduce a small
`edn.core` (or separately approved `edn_core`) boundary only for genuinely
universal contracts. Domain packs remain `edn.business` and future
`edn.personal`; current email code can stay `edn.memory`.

Potential dependency direction:

```text
foundation <- core contracts/runtime <- domain packs/connectors <- interfaces
                    ^
                    | adapters
              existing memory/retrieval/knowledge
```

Core must not import Streamlit, PnP scripts or concrete connector modules.
Connectors depend on SDK contracts. Business OS owns Project/Client/Risk etc.

## Compatibility gates

- Existing 124 Python tests remain passing throughout migration.
- Production email database opens unchanged and remains resumable/searchable.
- Retrieval ranking/citations have parity fixtures before consumer migration.
- Graph checkpoints/entities/relationships retain source keys.
- Streamlit Search, Ask EDN and Knowledge remain available until replacement
  features pass acceptance tests.
- SharePoint scripts retain independent approval and mutation constraints.

## Deprecate eventually

- email-only aliases such as `EmailEvidence` after mixed-source UI migration;
- environment-only provider selection after validated provider configuration;
- direct UI composition of stores after application-level context routing; and
- duplicated connector-specific progress/result shapes after standard Job
  adapters prove sufficient.

Deprecation requires migration telemetry, compatibility period and rollback; it
is not part of Alpha architecture documentation.

