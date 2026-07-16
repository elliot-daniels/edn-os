# Module 001 — Memory

> **Knowledge Compounds.**

**MOD-001** · Memory is a **durable EDN OS module** for capturing, storing, and searching personal and professional knowledge records locally with full provenance.

Outlook PST email archives are the **first data domain** implemented within Memory — not the permanent boundary of the module.

Implementation depends on **Module 000 — Foundation** and is delivered through short development sprints. Sprints schedule work; they do not define architecture.

---

## Purpose

Provide a local-first, read-only capability that:

1. Ingests source archives (Outlook PST in the initial implementation).
2. Preserves source provenance.
3. Extracts record metadata and attachments.
4. Stores structured records locally.
5. Supports basic keyword search.

---

## Future Data Domains (Not Authorised)

Memory may later extend to documents, photos, contacts, calendar entries, notes, and voice records. **None of these are authorised for implementation yet.** The initial implementation scope remains Outlook PST archives only.

---

## Motto Alignment

| Mission | Module Contribution |
|---------|---------------------|
| Capture knowledge once | Import archives into a canonical local store with provenance |
| Search everything instantly | Keyword search via SQLite FTS5 |
| Build systems that compound | Adapter-based ingest enables future data domains without rework |

---

## Initial Implementation Scope

| Capability | Description |
|------------|-------------|
| PST proof-of-concept | Compare libpff/pypff and readpst per `ARCHITECTURE.md`; select one adapter |
| PST import engine | Read-only ingest of one PST per import run |
| Memory database | SQLite with typed schema and FTS5 index |
| Keyword search | Query messages by keyword across subject, body, participants, attachment names |
| Provenance tracking | Normalised via `source_archives` and `import_runs`; fully resolved in search results |
| Partial-failure handling | Continue on record errors; machine-readable import report; retry support |
| Sensitivity defaults | All imported content starts as `unreviewed` (via Foundation `SensitivityStatus`) |
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
- Documents, photos, contacts, calendar, notes, voice records

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
| Foundation dependency | Uses Foundation configuration, logging, errors, types, and fingerprinting |
| Scope discipline | Smallest useful working version |

---

## User Stories

### US-1: Import PST

**As** an operator,
**I want** to import a PST archive into Memory,
**So that** historical email knowledge is captured locally with full provenance.

**Acceptance criteria:**

- PST is opened read-only.
- All readable messages in all folders are processed; every skipped or failed source record is accounted for.
- Metadata extracted: subject, participants (sender, to, cc, bcc), sent/received dates.
- Body text (and HTML if available) stored as derived content.
- Attachments saved under `E:\EDN OS\Data\Attachments\` with full attachment metadata.
- `source_archive` registered with path and SHA-256 fingerprint (via Foundation utility).
- Each message references `source_archive_id`, `import_run_id`, and `source_record_key`.
- Re-running import on the same archive does not create duplicate messages.
- Import completes with `warnings` status when partial failures occur.
- Machine-readable import report produced per run.
- Logs (via Foundation) record counts and error summaries; no message bodies.
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
| 1 | Architecture artefacts | `CONSTITUTION.md`, `ARCHITECTURE.md`, `SECURITY.md`, `MODULE-000-FOUNDATION.md`, this file |
| 2 | PST extraction PoC | Throwaway spikes for libpff and readpst; selection report in `docs/` |
| 3 | Python package | `src/edn/memory/` per `ARCHITECTURE.md` |
| 4 | SQLite schema | `source_archives`, `import_runs`, `messages`, `addresses`, `message_participants`, `attachments`, FTS5 |
| 5 | CLI | `import` and `search` commands |
| 6 | Tests | `tests/memory/` with synthetic fixtures in temp directories |
| 7 | `.gitignore` | Enforces no data/secrets in Git per `SECURITY.md` |

---

## Data Model Summary

See `ARCHITECTURE.md` for full logical schema (Memory-owned).

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

- [ ] Foundation (MOD-000) initial implementation complete
- [ ] PST PoC completed; adapter selected and documented (including Python version compatibility)
- [ ] Import processes a real PST without modifying it
- [ ] All readable messages imported; every skipped or failed record accounted for
- [ ] Attachments stored with full metadata; hashes recorded
- [ ] Keyword search returns correct results with resolved provenance
- [ ] Partial-failure and retry behaviour verified
- [ ] Unit tests pass in CI without real PST files
- [ ] No source content leaves the local machine
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

- Module 000 — Foundation (configuration, logging, errors, types, fingerprinting)
- Python (exact version compatibility validated during PoC)
- SQLite 3 with FTS5 enabled
- PST extraction library (selected after PoC)
- Approved encrypted data root with write access (`E:\EDN OS` production default)

---

© EDN Systems
