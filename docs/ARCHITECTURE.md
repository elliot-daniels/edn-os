# EDN OS Architecture

Implementation-oriented system structure for EDN OS. **Module 001 — Professional Memory** is the first durable module; its specification is in `MODULE-001-PROFESSIONAL-MEMORY.md`.

Development sprints deliver implementation work. They do not define architecture.

---

## System Overview

EDN OS is a modular platform of **source adapters**, a **domain model**, a **local store**, and a **search layer**. An **application service** orchestrates ingest workflows. Components communicate through domain contracts.

```
┌──────────────────────────────────────────────────────────────────┐
│                        EDN OS Platform                           │
├──────────────────────────────────────────────────────────────────┤
│  Application Service  ──orchestrates──▶  ingest → extract      │
│                                                    │             │
│                                                    ▼             │
│                                              store (SQLite)      │
├──────────────────────────────────────────────────────────────────┤
│  Search  ──queries via──▶  QueryRepository (domain contract)     │
└──────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
    Source (read-only)            E:\EDN OS data root
```

---

## Design Goals

1. **Adapter pattern for sources** — PST is the first adapter. Future adapters implement the same ingest contract.
2. **Provenance on every record** — resolved through `source_archives` and `import_runs`; no orphan data.
3. **Local-first storage** — SQLite database, attachments, and indexes under the approved encrypted data root.
4. **Keyword search in the initial implementation** — SQLite FTS5; no embeddings, vector databases, or knowledge graphs in Module 001.
5. **No GUI in Module 001** — CLI and programmatic interfaces only.
6. **Smallest useful version** — one PST per import run, one database, basic search.
7. **Partial-failure tolerance** — import continues after record-level errors; every skipped or failed record is accounted for.

---

## Data Root Layout

All runtime data lives outside the Git repository. `E:\EDN OS` is the Module 001 production default.

```
E:\EDN OS\
├── Source\
│   └── PST\                         # Operator-managed archives; read-only to EDN OS
├── Data\
│   ├── Databases\
│   │   └── professional_memory.db   # SQLite + FTS5
│   ├── Attachments\
│   │   └── {message_id}\
│   │       └── {storage_filename}
│   └── Indexes\                     # Reserved for non-SQLite indexes in future modules
├── Configuration\                   # Local settings; not committed to Git
├── Logs\
├── Exports\
└── Backups\
```

Paths are configurable via `Configuration\` (not committed to Git). Synthetic unit tests may use temporary local directories.

---

## Component Model

### 1. Ingest

Opens a source archive read-only and yields raw message references.

| Responsibility | Detail |
|----------------|--------|
| Input | Absolute path to a PST file |
| Output | Iterable of opaque message handles with folder context and `source_record_key` |
| Constraint | PST file is never opened for write |

**Contract:**

```
IngestAdapter.open(source_path) -> IngestSession
IngestSession.iter_messages() -> Iterator[RawMessageRef]
IngestSession.close()
```

Each `RawMessageRef` carries an adapter-generated `source_record_key` (see below).

### 2. Extract

Transforms raw message references into domain records.

| Responsibility | Detail |
|----------------|--------|
| Metadata | Subject, participants, dates, folder path |
| Body | Plain-text and/or HTML body stored as derived content |
| Attachments | Written to `Data\Attachments\`; metadata recorded in domain model |
| Sensitivity | All imported records default to `unreviewed` |
| Errors | Record-level failures raise domain errors; do not halt the import run |

**Contract:**

```
Extractor.extract(ref: RawMessageRef) -> MessageRecord
Extractor.extract_attachments(ref) -> list[AttachmentRecord]
```

### 3. Store

Persists domain records and manages attachment files. Implements storage contracts defined in the domain layer.

| Responsibility | Detail |
|----------------|--------|
| Database | SQLite at `Data\Databases\professional_memory.db` |
| Full-text | FTS5 virtual table synced with message content |
| Idempotency | Unique on (`source_archive_id`, `source_record_key`); re-import skips or updates — never duplicates silently |
| Deduplication | SHA-256 identifies duplicate attachment content; physical deduplication is deferred |

**Contract:**

```
MessageStore.upsert_message(record: MessageRecord) -> RecordId
MessageStore.upsert_attachment(record: AttachmentRecord) -> AttachmentId
QueryRepository.get_message(record_id) -> MessageRecord | None
QueryRepository.search(keywords: str, limit: int) -> list[SearchResult]
```

### 4. Search

Keyword queries via the `QueryRepository` contract. Search does not import ingest or extract implementations.

| Responsibility | Detail |
|----------------|--------|
| Query type | Keyword / phrase match (initial implementation) |
| Scope | Subject, body text, participant addresses, attachment `original_filename` values |
| Output | Ranked `SearchResult` list with **fully resolved provenance** |

### 5. Application Service

Orchestrates a single import run.

```
ImportService.run(source_path) -> ImportRunReport
```

Responsibilities: register or match `source_archive`, create `import_run`, iterate ingest → extract → store, handle partial failures, write machine-readable import report, set final run status.

### 6. Provenance

Provenance is normalised — not duplicated on every message row.

| Entity | Role |
|--------|------|
| `source_archives` | Registered PST path and fingerprint |
| `import_runs` | One execution of import against an archive |
| `messages.source_archive_id` | FK to archive |
| `messages.import_run_id` | FK to the run that created or last updated the record |
| `messages.source_record_key` | Adapter-stable identity within the archive |
| `messages.folder_path` | Folder hierarchy within the PST |

**SearchResult resolved provenance** (required fields):

- `source_path`, `source_fingerprint` (from `source_archives`)
- `import_run_id`
- `folder_path`, `source_record_key`
- `message_id` (internal UUID)

---

## Source Record Key

The ingest adapter generates a `source_record_key` for each message. Uniqueness is enforced on (`source_archive_id`, `source_record_key`).

Do **not** assume the PST-native message ID is always present or globally stable.

**Deterministic fallback** when no stable native ID is available:

```
source_record_key = SHA-256(
    folder_path + "\0" +
    normalized_subject + "\0" +
    ISO8601(sent_at or received_at or "") + "\0" +
    primary_sender_email + "\0" +
    str(body_byte_length) + "\0" +
    str(attachment_count)
)
```

When a stable native ID **is** available, the adapter may use it directly as `source_record_key`. The adapter must document which strategy applies per message.

---

## Canonical Record Schema (Logical)

### source_archives

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `source_type` | str | `outlook_pst` |
| `source_path` | str | Absolute path at registration |
| `source_fingerprint` | str | SHA-256 hex of archive file |
| `registered_at` | datetime | |

### import_runs

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `source_archive_id` | UUID | FK |
| `started_at` | datetime | |
| `completed_at` | datetime \| None | |
| `status` | str | `success`, `warnings`, `failed` |
| `report_path` | str | Machine-readable report on data root |
| `enumerated_count` | int | Messages seen by adapter |
| `imported_count` | int | Successfully stored |
| `skipped_count` | int | Already present; not re-imported |
| `failed_count` | int | Extraction or store failures |

### messages

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `source_archive_id` | UUID | FK |
| `import_run_id` | UUID | FK |
| `source_record_key` | str | Adapter-generated; unique per archive |
| `folder_path` | str | e.g. `Inbox/Projects/Bridge` |
| `subject` | str | |
| `sent_at` | datetime \| None | |
| `received_at` | datetime \| None | |
| `body_text` | str \| None | |
| `body_html` | str \| None | |
| `sensitivity_status` | str | See sensitivity values below |
| `imported_at` | datetime | |

**Unique constraint:** (`source_archive_id`, `source_record_key`)

### addresses

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `email_address` | str | Normalised lowercase |
| `display_name` | str \| None | Default display name if known |

### message_participants

| Field | Type | Notes |
|-------|------|-------|
| `message_id` | UUID | FK |
| `role` | str | `sender`, `to`, `cc`, `bcc` |
| `display_name` | str \| None | Per-message display name |
| `email_address` | str | |

### attachments

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `message_id` | UUID | FK |
| `original_filename` | str | Name from source |
| `storage_filename` | str | Sanitised name on disk |
| `attachment_index` | int | Zero-based position in source message |
| `extraction_status` | str | `pending`, `extracted`, `failed`, `skipped` |
| `extraction_error` | str \| None | Error detail when failed |
| `sha256` | str | Content hash; identifies duplicates |
| `size_bytes` | int \| None | |
| `content_type` | str \| None | MIME type if available |
| `storage_path` | str \| None | Path under `Data\Attachments\` |
| `sensitivity_status` | str | Same values as messages |

### sensitivity_status values

| Value | Meaning |
|-------|---------|
| `unreviewed` | Default for all imported former-employer content |
| `private_reference` | Operator-marked; reference only |
| `potentially_reusable` | Operator-marked; may be reusable |
| `restricted` | Operator-marked; restricted use |
| `quarantined` | Operator-marked; excluded from routine search |

No automated sensitivity classification in Module 001.

### FTS5 Index (`messages_fts`)

Indexed columns: `subject`, `body_text`, participant `email_address` values, attachment `original_filename` values linked to the message.

---

## Partial-Failure Behaviour

| Rule | Detail |
|------|--------|
| Continue on error | Record-level extraction or store failures do not abort the import run |
| Account for all | Every failed or skipped source record appears in the import report |
| No bodies in logs | Logs record counts, paths, and error summaries only |
| Import report | Machine-readable JSON written under `Logs\` or `Exports\` per run |
| Retry | Failed records may be retried in a subsequent import run against the same archive |
| Run status | `warnings` when any failures occurred but some records imported; `failed` when no records imported |
| Completion wording | All **readable** messages imported, with every skipped or failed source record accounted for |

---

## PST Extraction — Proof of Concept

The PST binary format is proprietary. **Do not commit to a library or build a production adapter until the PoC completes.**

### Candidates (PoC only)

| Option | Approach | Licence |
|--------|----------|---------|
| **A: libpff / pypff** | Direct PST parsing via Python bindings | LGPL |
| **B: readpst (libpst)** | Convert to maildir/mbox, parse RFC 822 | GPL |

Outlook COM (`win32com`) is out of scope for the PoC and Module 001.

### PoC evaluation criteria

Compare Option A and Option B only enough to select one production adapter:

- archive access
- folder and message enumeration
- metadata fidelity
- body fidelity
- attachment byte fidelity
- Unicode handling
- nested-folder handling
- performance on a representative archive
- dependency footprint
- platform fit
- licensing implications
- **Python version compatibility with the currently installed interpreter**

Do **not** build two production adapters before selecting one. PoC scripts are throwaway spikes.

### Recommended path

1. Spike Option A and Option B against one real PST under `E:\EDN OS\Source\PST\`.
2. Record results against the criteria above, including Python version support.
3. Select one adapter; implement a single production `IngestAdapter`.
4. Keep the `IngestAdapter` contract so a future swap remains possible.

---

## Module Layout (Python)

Code lives in the Git repository. No runtime data.

```
src/
└── edn_os/
    └── professional_memory/
        ├── domain/
        │   ├── models.py           # Canonical typed records
        │   ├── errors.py           # Domain exceptions
        │   └── contracts.py        # Protocols: IngestAdapter, Extractor, MessageStore, QueryRepository
        ├── application/
        │   └── import_service.py   # Orchestrates ingest → extract → store
        ├── ingest/
        │   └── pst/                # Single production adapter (post-PoC)
        ├── extract/
        ├── store/
        │   ├── database.py
        │   └── attachments.py
        ├── search/
        │   └── fts.py              # Implements QueryRepository search
        └── provenance/
            └── fingerprint.py

tests/
└── professional_memory/            # Uses temporary local directories
```

---

## Module 001 Exclusions

The following are **out of scope** for Module 001:

- GUI or web frontend
- Knowledge graph
- Embeddings or vector databases
- Cloud AI integration
- Microsoft 365 / SharePoint / Home Assistant / voice / vaults adapters
- Write-back or send actions on any source
- Executive Dashboard
- Automated sensitivity classification
- Physical attachment deduplication
- Encryption verification at runtime

---

## Testing Strategy

| Layer | Approach |
|-------|----------|
| Unit | In-memory SQLite and synthetic fixtures in temporary local directories |
| Integration | Manual import of a real PST under `E:\EDN OS\Source\PST\` (not CI) |
| Contract | Adapter and repository implementations tested against domain protocols |

Tests must not require real PST files in CI.

---

## Dependency Direction

```
domain/contracts  ◀── implemented by ── ingest, extract, store, search
domain/models     ◀── used by ── all components
application       ──▶ ingest, extract, store (via contracts)
search            ──▶ store.QueryRepository (via contract)
```

Concrete components do not import one another. The application service is the sole orchestrator of the ingest pipeline.

---

© EDN Systems
