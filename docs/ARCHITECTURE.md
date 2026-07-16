# EDN OS Architecture

Implementation-oriented system structure for EDN OS.

| Module | ID | Specification |
|--------|-----|---------------|
| Foundation | MOD-000 | `MODULE-000-FOUNDATION.md` |
| Memory | MOD-001 | `MODULE-001-MEMORY.md` |

Development sprints deliver implementation work. They do not define architecture.

---

## Platform Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                    MOD-000 — Foundation                         │
│  configuration · logging · platform errors · versioning       │
│  shared types · data-root policy · fingerprint_file · Connector │
└────────────────────────────┬────────────────────────────────────┘
                             │ depended on by
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        MOD-001 Memory   MOD-00N …     MOD-00N …
              │
              │  ingest → extract → store → search
              ▼
        Source (read-only)          E:\EDN OS data root
```

**Dependency rule:** `Foundation ← Memory ← (future modules)`. Foundation must **never** import Memory or any other feature module. Feature modules must not import one another.

---

## Ownership Split

### Foundation (MOD-000) owns

| Concern | Detail |
|---------|--------|
| Configuration | Typed settings, data-root validation, example config in Git |
| Logging | Common setup; modules call `get_logger(name)` |
| Platform errors | `EdnOsError` hierarchy |
| Version metadata | Application version, module/schema version conventions |
| Shared types | `RecordId`, timestamps, `ResultStatus`, `SensitivityStatus` |
| Data-root policy | Approved encrypted data root; `E:\EDN OS` production default |
| File fingerprinting | `fingerprint_file(path) -> SHA-256 hex` |
| Extension concept | Minimal `Connector` protocol — no registry or DI framework |

### Memory (MOD-001) owns

| Concern | Detail |
|---------|--------|
| Source archives | Registration, fingerprint application at import |
| Import runs | Orchestration, status, machine-readable reports |
| Domain models | Messages, participants, attachments, addresses |
| PST adapters | `IngestAdapter` and production PST implementation |
| Memory storage | SQLite schema, migrations, attachment files |
| Memory search | FTS5 keyword queries via `QueryRepository` |
| Domain errors | `ExtractionError`, `ImportRunError`, etc. |
| Application service | `ImportService` orchestrates ingest → extract → store |

Memory-specific contracts (`IngestAdapter`, `Extractor`, `MessageStore`, `QueryRepository`) remain in Memory — not moved to Foundation because they are not cross-module today.

---

## Data Root Layout

All runtime data lives outside the Git repository. Foundation defines the policy; Memory consumes configured paths.

```
E:\EDN OS\
├── Source\
│   └── PST\                         # Operator-managed; read-only to EDN OS
├── Data\
│   ├── Databases\
│   │   └── memory.db                # Memory SQLite + FTS5
│   ├── Attachments\                 # Memory attachment storage
│   └── Indexes\                     # Reserved for future modules
├── Configuration\                   # Real settings; excluded from Git
├── Logs\                            # Foundation-configured log output
├── Exports\
└── Backups\
```

Example configuration is committed to Git (e.g. `config/settings.example.toml`). Synthetic unit tests may use temporary local directories.

---

## Memory Component Model

### 1. Ingest

Opens a source archive read-only and yields raw message references.

```
IngestAdapter.open(source_path) -> IngestSession
IngestSession.iter_messages() -> Iterator[RawMessageRef]
IngestSession.close()
```

Each `RawMessageRef` carries an adapter-generated `source_record_key`.

### 2. Extract

```
Extractor.extract(ref: RawMessageRef) -> MessageRecord
Extractor.extract_attachments(ref) -> list[AttachmentRecord]
```

Record-level failures raise Memory domain errors; they do not halt the import run.

### 3. Store

```
MessageStore.upsert_message(record: MessageRecord) -> RecordId
MessageStore.upsert_attachment(record: AttachmentRecord) -> AttachmentId
QueryRepository.get_message(record_id) -> MessageRecord | None
QueryRepository.search(keywords: str, limit: int) -> list[SearchResult]
```

Database: `Data\Databases\memory.db`. Idempotency: unique on (`source_archive_id`, `source_record_key`).

### 4. Search

Keyword queries via `QueryRepository`. Search does not import ingest or extract implementations.

### 5. Application Service

```
ImportService.run(source_path) -> ImportRunReport
```

Uses Foundation logging and `fingerprint_file` for archive registration.

### 6. Provenance

Normalised via `source_archives` and `import_runs`. **SearchResult** must expose fully resolved provenance: `source_path`, `source_fingerprint`, `import_run_id`, `folder_path`, `source_record_key`, `message_id`.

---

## Source Record Key

Uniqueness enforced on (`source_archive_id`, `source_record_key`). Do not assume PST-native message IDs are always present or stable.

**Deterministic fallback:**

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

When a stable native ID is available, the adapter may use it directly.

---

## Memory Logical Schema

### source_archives

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `source_type` | str | `outlook_pst` |
| `source_path` | str | Absolute path at registration |
| `source_fingerprint` | str | SHA-256 via Foundation utility |
| `registered_at` | datetime | |

### import_runs

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `source_archive_id` | UUID | FK |
| `started_at`, `completed_at` | datetime | |
| `status` | str | `success`, `warnings`, `failed` |
| `report_path` | str | Machine-readable JSON |
| `enumerated_count`, `imported_count`, `skipped_count`, `failed_count` | int | |

### messages

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `source_archive_id`, `import_run_id` | UUID | FK |
| `source_record_key` | str | Unique per archive |
| `folder_path`, `subject` | str | |
| `sent_at`, `received_at` | datetime \| None | |
| `body_text`, `body_html` | str \| None | |
| `sensitivity_status` | SensitivityStatus | Default `unreviewed` |
| `imported_at` | datetime | |

### addresses · message_participants · attachments

See `MODULE-001-MEMORY.md`. Attachment fields include `original_filename`, `storage_filename`, `attachment_index`, `extraction_status`, `extraction_error`, `sha256`, `size_bytes`, `content_type`, `storage_path`, `sensitivity_status`. Hashes identify duplicates; physical deduplication deferred.

### FTS5 (`messages_fts`)

Indexed: `subject`, `body_text`, participant emails, attachment `original_filename` values.

---

## Partial-Failure Behaviour (Memory)

| Rule | Detail |
|------|--------|
| Continue on error | Record-level failures do not abort the import run |
| Account for all | Every failed/skipped record in import report |
| No bodies in logs | Foundation logging policy applies |
| Import report | Machine-readable JSON per run |
| Retry | Failed records eligible on subsequent import run |
| Completion | All **readable** messages imported; every skipped or failed record accounted for |

---

## PST Extraction — Proof of Concept (Memory)

Compare **libpff/pypff** and **readpst** only enough to select one production adapter. Evaluate: archive access, enumeration, metadata/body/attachment fidelity, Unicode, nested folders, performance, dependencies, platform fit, licensing, **Python version compatibility**.

Do not build two production adapters. PoC scripts are throwaway spikes. Outlook COM is out of scope.

---

## Module Layout (Python)

```
src/
└── edn/
    ├── foundation/                  # MOD-000
    │   ├── config.py
    │   ├── logging.py
    │   ├── errors.py
    │   ├── types.py
    │   ├── versioning.py
    │   ├── fingerprint.py
    │   └── connector.py             # Minimal protocol only
    └── memory/                      # MOD-001
        ├── domain/
        │   ├── models.py
        │   ├── errors.py
        │   └── contracts.py
        ├── application/
        │   └── import_service.py
        ├── ingest/pst/
        ├── extract/
        ├── store/
        └── search/

config/
└── settings.example.toml            # Safe example; committed

tests/
├── foundation/
└── memory/
```

---

## Module Exclusions

### Foundation (MOD-000)

No PST parsing, email models, SQLite business schemas, search, FTS5, AI, GUI, network services, event bus, DI framework, authentication, or secrets vault. See `MODULE-000-FOUNDATION.md`.

### Memory (MOD-001)

No GUI, knowledge graph, embeddings, vector DB, cloud AI, M365/SharePoint/Home Assistant/voice adapters, dashboard, write-back, automated sensitivity classification, or physical attachment deduplication. PST-only for initial implementation. See `MODULE-001-MEMORY.md`.

---

## Testing Strategy

| Layer | Approach |
|-------|----------|
| Foundation unit | Config validation, logging, fingerprint, errors — temp directories |
| Memory unit | In-memory SQLite, synthetic fixtures — temp directories |
| Memory integration | Manual PST import under `E:\EDN OS\Source\PST\` (not CI) |

Foundation tests must not import Memory. Memory tests may import Foundation.

---

## Versioning and ADRs

| Concept | Owner |
|---------|-------|
| Module IDs (`MOD-000`, `MOD-001`) | Foundation convention |
| Application semver | Foundation |
| `{module}.schema_version` | Owning module declares; Foundation documents convention |
| ADR numbering (`ADR-NNN`) | Reserved; create only when a significant decision requires one |

Do not invent database migrations before a module defines a schema.

---

## Dependency Direction

```
foundation
    ▲
    │ (imports only)
memory:  domain ← application ← ingest, extract, store, search
```

Concrete Memory components do not import one another. `ImportService` is the sole ingest-pipeline orchestrator. Search accesses storage through `QueryRepository` only.

---

© EDN Systems
