# Module 003 — Structured Knowledge Extraction

Module 003 derives a local, deterministic knowledge layer from canonical emails.
It does not change email rows and every entity or relationship resolves to one
or more `source_record_key` values in Memory.

## Pipeline

```text
bounded email page -> named/identifier/person rules -> normalized mentions
                   -> co-occurrence relationships -> atomic graph persistence
                   -> email-id checkpoint
```

The pipeline reads at most 250 emails per page and commits the page's mentions,
relationships, sources, and final checkpoint atomically. Restarting resumes after
the last committed SQLite email ID and safely reprocesses an interrupted page.
A second run with no new email is a no-op.
`rule_version` prevents silently mixing results from incompatible rule sets; a
future rebuild command can deliberately regenerate the graph after rule changes.

Run locally with:

```bash
python -m edn.knowledge_graph.pipeline /path/to/edn-memory.db
```

## Schema

| Table | Purpose |
|---|---|
| `knowledge_entities` | Unique `(entity_type, normalized_name)` identities |
| `knowledge_entity_occurrences` | Field-level mentions linked to source emails |
| `knowledge_relationships` | Unique typed entity edges |
| `knowledge_relationship_sources` | Source emails supporting each edge |
| `knowledge_extraction_state` | Rule version and last committed email ID |

Entities are normalized for identity while retaining a canonical display name.
Occurrence and relationship-source tables are the evidence model; no extracted
fact exists without a source key.

## Rules and relationships

`rules.py` contains configurable named patterns for projects, clients,
technologies, equipment, sites, and skills plus generic CRQ, ticket, and hostname
patterns. Senders become people using RFC address parsing. The extractor creates:

- person `works_on` project
- project `uses` technology or equipment
- client `associated_with` project
- incident `affects` site
- technology/equipment `commissioned_at` site when commissioning language exists

These are transparent co-occurrence assertions, not inferred causality. Adding a
named pattern or relationship rule requires a rule-version increment and graph
rebuild so incremental results remain consistent.

## Retrieval and UI

`KnowledgeCandidateRetriever` looks up matching entities and returns a bounded
set of their supporting emails. `RetrievalEngine` merges those candidates by
source key with FTS5 candidates before deterministic reranking. Ask EDN still
receives only original email evidence, so existing citation validation remains
unchanged.

The Knowledge tab lists bounded entities by category and evidence count. Selecting
an entity shows its generated summary, adjacent relationships, and supporting
emails through read-only service APIs.

## Future extraction points

The extractor and persistence boundary permits future local semantic or model-
assisted candidate extraction. Such extractors must emit the same `EntityMention`
and `RelationshipFact` models, identify their rule/model version, and preserve
source keys. Embeddings, cloud AI, documents, and autonomous workflows are not
part of Module 003.
