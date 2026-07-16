# Module 001 — Professional Memory

> **Knowledge Compounds.**

Professional Memory is a **durable EDN OS module**. It captures historical correspondence locally, preserves provenance, and makes it searchable. This document defines the module's permanent scope, contracts, and acceptance criteria.

Implementation is delivered through short development sprints. Sprints schedule and track work; they do not define software architecture. Architecture lives in `CONSTITUTION.md`, `ARCHITECTURE.md`, `SECURITY.md`, and module specifications such as this file.

---

## Purpose

Provide a local-first, read-only capability that:

1. Ingests an Outlook PST archive.
2. Preserves source provenance.
3. Extracts message metadata and attachments.
4. Stores structured records locally.
5. Supports basic keyword search.

---

## Motto Alignment

| Mission | Module Contribution |
|---------|---------------------|
| Capture knowledge once | Import PST into a canonical local store with provenance |
| Search everything instantly | Keyword search via SQLite FTS5 |
| Build systems that compound | Adapter-based ingest enables future sources without rework |

---

## Initial Implementation Scope

The first working version of this module includes:

| Capability | Description |
|------------|-------------|
| PST proof-of-concept | Evaluate extraction libraries against a real PST (see `ARCHITECTURE.md`) |
| PST import engine | Read-only ingest of one PST into the local store |
| Knowledge database | SQLite with typed schema and FTS5 index |
| Keyword search | Query messages by keyword across subject, body, sender, attachment names |
| Provenance tracking | Every record links to PST path, folder, and message ID |
| Automated tests | Unit tests for extract, store, and search (no real PST in CI) |
| CLI entry point | Command to import a PST and command to search (no GUI) |

---

## Out of Scope

The following are excluded from Module 001 and must not appear in its implementation:

- GUI or web interface
- Knowledge graph
- Embeddings or vector databases
- Cloud AI integration (no source content uploaded)
- Microsoft 365, SharePoint, Home Assistant, voice, or personal vault adapters
- Executive Dashboard
- Write-back, send, or delete actions on any source
- Multi-PST concurrent import (single PST per import run is sufficient for the initial implementation)

---

## Constraints

| Constraint | Requirement |
|------------|-------------|
| Source integrity | Original PST never modified |
| Data locality | Raw source and extracted content on encrypted E: drive |
| Repository content | Git holds code and documentation only |
| AI boundary | No source email content sent to cloud AI |
| Source of truth | Stored records with provenance — not AI output |
| Access model | Read-only by default |
| Future external actions | Require human approval (not built in the initial implementation) |
| Scope discipline | Smallest useful working version |

---

## User Stories

### US-1: Import PST

**As** an operator,
**I want** to import a PST archive into Professional Memory,
**So that** historical email knowledge is captured locally with full provenance.

**Acceptance criteria:**

- PST is opened read-only.
- All messages in all folders are processed.
- Metadata extracted: subject, sender, recipients, sent/received dates.
- Body text (and HTML if available) stored as derived content.
- Attachments saved to E: drive with SHA-256 checksum.
- Each record contains `source_path`, `source_fingerprint`, `folder_path`, `message_id`.
- Re-running import on the same PST does not create duplicate records.
- Import logs record counts and errors; no message bodies in logs.

### US-2: Search Messages

**As** an operator,
**I want** to search imported messages by keyword,
**So that** I can find relevant historical correspondence quickly.

**Acceptance criteria:**

- Search matches against subject, body text, sender, and linked attachment filenames.
- Results include provenance fields (source path, folder, message ID).
- Search operates fully offline.
- Results are ranked by FTS5 relevance.

### US-3: Trace Provenance

**As** an operator,
**I want** every search result to show its origin,
**So that** I can verify where a record came from.

**Acceptance criteria:**

- Every `SearchResult` includes `source_path`, `folder_path`, `message_id`, and `source_fingerprint`.
- Attachment records link back to their parent message and source.

---

## Implementation Artefacts

Work is delivered incrementally through development sprints. The following artefacts complete the initial implementation:

| # | Item | Reference |
|---|------|-----------|
| 1 | Architecture artefacts | `CONSTITUTION.md`, `ARCHITECTURE.md`, `SECURITY.md`, this file |
| 2 | PST extraction PoC | Two adapter spikes (libpff and readpst); comparison report in `docs/` |
| 3 | Python package | `src/edn_os/professional_memory/` per `ARCHITECTURE.md` |
| 4 | SQLite schema | Migrations for messages, attachments, FTS5 |
| 5 | CLI | `import` and `search` commands |
| 6 | Tests | `tests/professional_memory/` with synthetic fixtures |
| 7 | `.gitignore` | Enforces no data/secrets in Git per `SECURITY.md` |

---

## Data Model Summary

See `ARCHITECTURE.md` for full logical schema.

**Tables:**

- `messages` — canonical message records with provenance
- `attachments` — file metadata and E: drive storage path
- `messages_fts` — FTS5 virtual table (subject, body_text, sender)

---

## CLI Commands (Planned)

```
edn-os memory import --pst E:\edn-os\sources\archive.pst
edn-os memory search "bridge foundation"
```

Exact command names may be adjusted during implementation; behaviour must match acceptance criteria.

---

## Initial Implementation Complete

- [ ] PST PoC completed; adapter selected and documented
- [ ] Import processes a real PST on E: drive without modifying it
- [ ] All messages and attachments stored with provenance
- [ ] Keyword search returns correct results offline
- [ ] Unit tests pass in CI without real PST files
- [ ] No source content leaves the local machine
- [ ] `.gitignore` prevents data and secrets from being committed
- [ ] Code uses type annotations throughout

---

## Risks

| Risk | Mitigation |
|------|------------|
| PST library incompatibility | PoC before committing; adapter interface allows swap |
| Large PST performance | Log progress; process messages iteratively; optimise in a later implementation phase if needed |
| Encrypted E: drive unavailable in dev | Configurable data root with startup validation; dev may use E: or fail loudly |
| Attachment filename collisions | Namespace by record ID in storage path |

---

## Dependencies

- Python 3.11+ (typed modules)
- SQLite 3 with FTS5 enabled
- PST extraction library (selected after PoC)
- Encrypted E: drive with write access

---

## Later Modules (Not Specified Here)

Future EDN OS modules may extend the platform without redefining this module:

- Additional source adapters (M365, SharePoint)
- Executive Dashboard
- Semantic / vector search
- Controlled AI summarisation with human approval
- GUI

---

© EDN Systems
