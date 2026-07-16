# EDN OS Architecture

Implementation-oriented system structure for EDN OS. **Module 001 — Professional Memory** is the first durable module; its specification is in `MODULE-001-PROFESSIONAL-MEMORY.md`.

Development sprints deliver implementation work. They do not define architecture.

---

## System Overview

EDN OS is a modular platform of **source adapters**, a **canonical record model**, a **local store**, and a **search layer**. Each durable module extends the platform without rewriting prior work.

```
┌─────────────────────────────────────────────────────────────┐
│                     EDN OS Platform                         │
├─────────────┬──────────────┬──────────────┬─────────────────┤
│   Ingest    │   Extract    │    Store     │     Search      │
│  (adapters) │  (parsers)   │  (SQLite)    │    (FTS5)       │
└──────┬──────┴──────┬───────┴──────┬───────┴────────┬────────┘
       │             │              │                │
       ▼             ▼              ▼                ▼
   Source         Canonical      E: drive         Keyword
   (read-only)    Records +      encrypted        queries
                  Provenance     local files
```

---

## Design Goals

1. **Adapter pattern for sources** — PST is the first adapter. Future adapters (M365, SharePoint, etc.) implement the same ingest contract.
2. **Provenance on every record** — no orphan data.
3. **Local-first storage** — SQLite database and attachment files on the encrypted E: drive.
4. **Keyword search in the initial implementation** — SQLite FTS5; no embeddings, vector databases, or knowledge graphs in Module 001.
5. **No GUI in Module 001** — CLI and programmatic interfaces only.
6. **Smallest useful version** — one PST, one database, basic search.

---

## Component Model

### 1. Ingest

Opens a source archive read-only and yields raw message references.

| Responsibility | Detail |
|----------------|--------|
| Input | Absolute path to a PST file on the E: drive |
| Output | Iterable of opaque message handles with folder context |
| Constraint | PST file is never opened for write; no in-place changes |

**Interface contract (conceptual):**

```
IngestAdapter.open(source_path) -> IngestSession
IngestSession.iter_messages() -> Iterator[RawMessageRef]
IngestSession.close()
```

### 2. Extract

Transforms raw message references into canonical records.

| Responsibility | Detail |
|----------------|--------|
| Metadata | Subject, sender, recipients, dates, folder path, message ID |
| Body | Plain-text and/or HTML body stored as derived content |
| Attachments | Written to E: drive; database holds path + checksum |
| Provenance | Every record links to PST path, folder, and message identifier |

**Interface contract (conceptual):**

```
Extractor.extract(ref: RawMessageRef) -> MessageRecord
Extractor.extract_attachments(ref) -> list[AttachmentRecord]
```

### 3. Store

Persists canonical records and manages attachment files.

| Responsibility | Detail |
|----------------|--------|
| Database | SQLite on E: drive (`professional_memory.db`) |
| Full-text | FTS5 virtual table synced with message content |
| Attachments | Files under `E:\edn-os\data\attachments\` (path configurable) |
| Idempotency | Re-import of the same message updates nothing or records a skip — never duplicates silently |

**Interface contract (conceptual):**

```
Store.upsert_message(record: MessageRecord) -> RecordId
Store.upsert_attachment(record: AttachmentRecord) -> AttachmentId
Store.get_message(record_id) -> MessageRecord | None
```

### 4. Search

Keyword queries against FTS5 index.

| Responsibility | Detail |
|----------------|--------|
| Query type | Keyword / phrase match (initial implementation) |
| Scope | Message subject, body text, attachment filenames |
| Output | Ranked list of record IDs with provenance metadata |

**Interface contract (conceptual):**

```
Search.query(keywords: str, limit: int) -> list[SearchResult]
```

### 5. Provenance

Cross-cutting concern embedded in every stored record.

| Field | Purpose |
|-------|---------|
| `source_type` | e.g. `outlook_pst` |
| `source_path` | Absolute path to the PST at import time |
| `source_fingerprint` | SHA-256 of PST file (detect moved/renamed archives) |
| `folder_path` | Folder hierarchy within the PST |
| `message_id` | Stable identifier from the PST adapter |

---

## Data Layout (E: Drive)

All runtime data lives outside the Git repository.

```
E:\edn-os\
├── data\
│   ├── professional_memory.db      # SQLite + FTS5
│   └── attachments\
│       └── {record_id}\
│           └── {filename}
├── logs\
│   └── professional_memory.log
└── sources\                        # Operator-managed; not created by EDN OS
    └── *.pst                       # Read-only; never modified by EDN OS
```

Paths are configurable via a local settings file on E: (not committed to Git).

---

## Canonical Record Schema (Logical)

### MessageRecord

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Internal primary key |
| `source_type` | str | `outlook_pst` |
| `source_path` | str | PST absolute path |
| `source_fingerprint` | str | SHA-256 hex |
| `folder_path` | str | e.g. `Inbox/Projects/Bridge` |
| `message_id` | str | Adapter-native stable ID |
| `subject` | str | |
| `sender` | str | |
| `recipients_to` | str | Serialized in the initial implementation |
| `recipients_cc` | str | Serialized in the initial implementation |
| `sent_at` | datetime \| None | |
| `received_at` | datetime \| None | |
| `body_text` | str \| None | |
| `body_html` | str \| None | |
| `imported_at` | datetime | |

### AttachmentRecord

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | |
| `message_id` | UUID | FK to MessageRecord |
| `filename` | str | Original name |
| `content_type` | str \| None | MIME type if available |
| `size_bytes` | int | |
| `sha256` | str | Content hash |
| `storage_path` | str | Path on E: drive |

### FTS5 Index

Indexed columns: `subject`, `body_text`, `sender`, attachment `filename` values linked to the message.

---

## PST Extraction — Options and Recommendation

The PST binary format is proprietary. The adapter choice affects metadata fidelity, attachment handling, licensing, and platform support. **Do not commit to a library until a proof-of-concept validates against a representative PST.**

### Option A: `libpff` / `pypff`

| Aspect | Assessment |
|--------|------------|
| Approach | Direct PST parsing via libpff Python bindings |
| Pros | No Outlook dependency; reads PST natively; good metadata access |
| Cons | Binding maintenance varies by platform; Windows build tooling may be needed |
| Licence | LGPL (libpff) |

### Option B: `readpst` (libpst) → maildir

| Aspect | Assessment |
|--------|------------|
| Approach | Convert PST to maildir/mbox, then parse RFC 822 messages |
| Pros | Mature converter; simple downstream parsing (`email` stdlib) |
| Cons | Extra conversion step; temp disk use; potential metadata loss in conversion |
| Licence | GPL (libpst) |

### Option C: Outlook COM (`win32com`)

| Aspect | Assessment |
|--------|------------|
| Approach | Automate Outlook on Windows to export messages |
| Pros | Highest fidelity when Outlook is installed |
| Cons | Requires Outlook licence; not headless-friendly; Windows-only; automation fragility |
| Licence | Depends on Outlook installation |

### Recommended Path

1. **Proof-of-concept** — implement thin adapters for Option A and Option B against one real PST on the E: drive.
2. **Evaluate** — compare: message count, subject/sender/date accuracy, attachment byte-identical extraction, import speed, and dependency footprint.
3. **Decide** — select one adapter for the initial implementation; keep the `IngestAdapter` interface so the other remains swappable.

---

## Module Layout (Python)

Code lives in the Git repository. No runtime data.

```
src/
└── edn_os/
    └── professional_memory/
        ├── __init__.py
        ├── ingest/
        │   ├── adapter.py          # IngestAdapter protocol
        │   └── pst/                # PST-specific adapters (post-PoC)
        ├── extract/
        │   └── message.py          # RawMessageRef → MessageRecord
        ├── store/
        │   ├── database.py         # SQLite connection and migrations
        │   ├── models.py             # Typed record dataclasses
        │   └── attachments.py      # File write + hash
        ├── search/
        │   └── fts.py              # FTS5 queries
        └── provenance/
            └── fingerprint.py      # SHA-256 source fingerprinting

tests/
└── professional_memory/
    ├── test_extract.py
    ├── test_store.py
    ├── test_search.py
    └── fixtures/                   # Synthetic/minimal test data only
```

---

## Module 001 Exclusions

The following are **out of scope** for Module 001 and must not appear in its implementation:

- GUI or web frontend
- Knowledge graph
- Embeddings or vector databases
- Cloud AI integration
- Microsoft 365 / SharePoint / Home Assistant / voice / vaults adapters
- Write-back or send actions on any source
- Executive Dashboard

---

## Testing Strategy

| Layer | Approach |
|-------|----------|
| Unit | Typed functions tested with in-memory SQLite and synthetic message fixtures |
| Integration | Import a small fixture PST on E: drive in a manual test script (not CI) |
| Contract | Each adapter implements `IngestAdapter`; tested via shared conformance tests |

Tests must not require real PST files in CI. Use generated RFC 822 fixtures for extract/store/search tests.

---

## Dependency Direction

```
ingest → extract → store → search
              ↓
         provenance (used by extract and store)
```

Modules may not import upward (e.g. `search` must not import `ingest`). Shared types live in `store/models.py`.

---

© EDN Systems
