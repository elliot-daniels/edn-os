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

| Capability | Description |
|------------|-------------|
| PST proof-of-concept | Compare libpff/pypff and readpst per `ARCHITECTURE.md`; select one adapter |
| PST import engine | Read-only ingest of one PST per import run |
| Knowledge database | SQLite with typed schema and FTS5 index |
| Keyword search | Query messages by keyword across subject, body, participants, attachment names |
| Provenance tracking | Normalised via `source_archives` and `import_runs`; fully resolved in search results |
| Partial-failure handling | Continue on record errors; machine-readable import report; retry support |
| Sensitivity defaults | All imported content starts as `unreviewed` |
| Automated tests | Unit tests in temporary local directories; no real PST in CI |
| CLI entry point | Commands to import a PST and search (no GUI) |

---

## Out of Scope

- GUI or web interface
- Knowledge graph
- Embeddings or vector databases
- Cloud AI integration (no source content uploaded)
- Microsoft 365, SharePoint, Home Assistant, voice, or personal vault adapters
- Executive Dashboard
- Write-back, send, or delete actions on any source
- Multi-PST concurrent import (single PST per import run is sufficient)
- Automated sensitivity classification
- Physical attachment deduplication
- Encryption verification at runtime
- Outlook COM (`win32com`) adapter

---

## Constraints

| Constraint | Requirement |
|------------|-------------|
| Source integrity | Original PST never modified |
| Data locality | Raw source and extracted content under approved encrypted data root (`E:\EDN OS` production default) |
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
- All readable messages in all folders are processed; every skipped or failed source record is accounted for.
- Metadata extracted: subject, participants (sender, to, cc, bcc), sent/received dates.
- Body text (and HTML if available) stored as derived content.
- Attachments saved under `E:\EDN OS\Data\Attachments\` with full attachment metadata.
- `source_archive` registered with path and SHA-256 fingerprint.
- Each message references `source_archive_id`, `import_run_id`, and `source_record_key`.
- Re-running import on the same archive does not create duplicate messages.
- Import completes with `warnings` status when partial failures occur.
- Machine-readable import report produced per run.
- Logs record counts and error summaries; no message bodies in logs.
- All imported messages and attachments have `sensitivity_status = unreviewed`.

### US-2: Search Messages

**As** an operator,
**I want** to search imported messages by keyword,
**So that** I can find relevant historical correspondence quickly.

**Acceptance criteria:**

- Search matches against subject, body text, participant addresses, and linked attachment `original_filename` values.
- Results include fully resolved provenance: `source_path`, `source_fingerprint`, `import_run_id`, `folder_path`, `source_record_key`.
- Search operates fully offline.
- Results are ranked by FTS5 relevance.
- Records with `sensitivity_status = quarantined` are excluded from routine search.

### US-3: Trace Provenance

**As** an operator,
**I want** every search result to show its origin,
**So that** I can verify where a record came from.

**Acceptance criteria:**

- Every `SearchResult` resolves provenance through `source_archives` — not duplicated per-row fields alone.
- Attachment records link back to their parent message, `source_archive`, and `import_run`.

### US-4: Retry Failed Records

**As** an operator,
**I want** to re-run import against the same archive,
**So that** previously failed records can be retried without duplicating successful imports.

**Acceptance criteria:**

- Failed records from a prior run are eligible for extraction on retry.
- Successfully imported records are skipped (not duplicated).
- New import run creates a new `import_run` with its own report.

---

## Implementation Artefacts

| # | Item | Reference |
|---|------|-----------|
| 1 | Architecture artefacts | `CONSTITUTION.md`, `ARCHITECTURE.md`, `SECURITY.md`, this file |
| 2 | PST extraction PoC | Throwaway spikes for libpff and readpst; selection report in `docs/` |
| 3 | Python package | `src/edn_os/professional_memory/` per `ARCHITECTURE.md` |
| 4 | SQLite schema | `source_archives`, `import_runs`, `messages`, `addresses`, `message_participants`, `attachments`, FTS5 |
| 5 | CLI | `import` and `search` commands |
| 6 | Tests | `tests/professional_memory/` with synthetic fixtures in temp directories |
| 7 | `.gitignore` | Enforces no data/secrets in Git per `SECURITY.md` |

---

## Data Model Summary

See `ARCHITECTURE.md` for full logical schema.

**Tables:** `source_archives`, `import_runs`, `messages`, `addresses`, `message_participants`, `attachments`, `messages_fts`

---

## CLI Commands (Planned)

```
edn-os memory import --pst "E:\EDN OS\Source\PST\archive.pst"
edn-os memory search "bridge foundation"
```

Exact command names may be adjusted during implementation; behaviour must match acceptance criteria.

---

## Initial Implementation Complete

- [ ] PST PoC completed; adapter selected and documented (including Python version compatibility)
- [ ] Import processes a real PST without modifying it
- [ ] All readable messages imported; every skipped or failed record accounted for
- [ ] Attachments stored with full metadata; hashes recorded
- [ ] Keyword search returns correct results with resolved provenance
- [ ] Partial-failure and retry behaviour verified
- [ ] Unit tests pass in CI without real PST files
- [ ] No source content leaves the local machine
- [ ] `.gitignore` prevents data and secrets from being committed
- [ ] Code uses type annotations throughout

---

## Risks

| Risk | Mitigation |
|------|------------|
| PST library incompatibility | PoC validates Python version support; adapter contract allows swap |
| Unstable PST message IDs | Deterministic `source_record_key` fallback |
| Large PST performance | Iterative processing; progress in import report |
| Attachment filename collisions | `storage_filename` sanitisation; namespace by `message_id` |
| Partial extraction failures | Continue-on-error; machine-readable report; retry on re-import |

---

## Dependencies

- Python (exact version compatibility validated during PoC)
- SQLite 3 with FTS5 enabled
- PST extraction library (selected after PoC)
- Approved encrypted data root with write access (`E:\EDN OS` production default)

---

## Later Modules (Not Specified Here)

- Additional source adapters (M365, SharePoint)
- Executive Dashboard
- Semantic / vector search
- Controlled AI summarisation with human approval
- Automated sensitivity classification
- Physical attachment deduplication
- GUI

---

© EDN Systems
