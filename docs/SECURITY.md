# EDN OS Security Model

Security requirements and controls for EDN OS. Applies platform-wide. Module 001 initial-implementation controls are marked **M001**.

---

## Threat Model (Module 001)

| Threat | Impact | Control |
|--------|--------|---------|
| Source archive tampering | Loss of trust in provenance | Read-only PST access; fingerprint at import **(M001)** |
| Data exfiltration to cloud AI | Confidential email disclosure | No source content sent to cloud AI in the initial implementation **(M001)** |
| Secrets in Git | Credential leak | Repository contains code and docs only; secrets on E: **(M001)** |
| Unencrypted data at rest | Exposure if device lost | All runtime data on encrypted E: drive **(M001)** |
| Duplicate/orphan records | Incorrect search results | Provenance required on every record; idempotent import **(M001)** |
| Unauthorized write-back | Unintended external action | Read-only by default; human approval gate for future actions **(M001)** |

---

## Data Classification

| Class | Examples | Storage | Git |
|-------|----------|---------|-----|
| **Source** | PST archives | E: drive (operator-managed) | Never |
| **Derived** | Extracted bodies, attachments | E: drive under `data/` | Never |
| **Index** | SQLite DB, FTS5 tables | E: drive | Never |
| **Operational** | Import logs | E: drive under `logs/` | Never |
| **Secret** | API keys, passwords, tokens | E: drive or OS credential store | Never |
| **Code** | Python modules, tests | Git repository | Yes |
| **Documentation** | Architecture and module docs | Git repository | Yes |

---

## Storage Rules

1. **Encrypted E: drive** is the sole location for source PST files, extracted content, databases, indexes, and logs.
2. EDN OS must refuse to start import or store operations if the configured data root is not on the E: drive (path validation at startup).
3. Attachment files are written with restrictive permissions (owner read/write only where the OS supports it).

---

## Source Handling

| Rule | Detail |
|------|--------|
| Read-only access | PST files opened in read-only mode; no create, update, or delete on source |
| No relocation | EDN OS does not move or rename operator PST files |
| Fingerprinting | SHA-256 hash computed at import; stored as `source_fingerprint` |
| Provenance | Every record stores `source_path`, `folder_path`, and `message_id` |

---

## AI and External Services (Module 001)

| Rule | Detail |
|------|--------|
| No cloud upload | Message bodies, headers, metadata, and attachment content must not be transmitted to external AI services |
| No network dependency | Import, store, and search operate fully offline |
| AI is not authoritative | When AI is introduced in future modules, outputs reference record IDs; stored records remain the source of truth |

---

## Human Approval Gate (Future)

Any action that transmits data outside the local E: drive boundary requires:

1. Explicit operator initiation.
2. Display of what will be sent and to which service.
3. Confirmed approval before execution.

The initial implementation of Module 001 provides **no external actions**; this gate is documented but not built.

---

## Repository Hygiene

The Git repository must contain **code and documentation only**.

### Must Never Be Committed

- `*.pst` and other mail archives
- Extracted attachment files
- SQLite databases (`*.db`, `*.sqlite`, `*.sqlite3`)
- Search index files
- Runtime logs
- `.env`, credentials, API keys, tokens
- Operator data directories (`data/`, `logs/`, `sources/`)

A `.gitignore` must enforce these patterns before the first application commit.

---

## Secrets Management

- No secrets in source code, tests, or documentation.
- Local configuration (data root path, optional future API keys) lives in a settings file on the E: drive.
- Settings file is excluded from Git.

---

## Logging

| Rule | Detail |
|------|--------|
| Location | `E:\edn-os\logs\` only |
| Content | Operational events (import start/end, counts, errors); no full message bodies in logs |
| Retention | Operator-managed; not committed to Git |

---

## Input Validation

- Source paths must be validated (exist, readable, `.pst` extension for Module 001 PST ingest).
- Search queries are parameterised through SQLite — no string-concatenated SQL.
- Attachment filenames are sanitised before writing to disk (path traversal prevention).

---

## Module 001 Security Checklist

- [ ] PST opened read-only only
- [ ] Data root restricted to encrypted E: drive
- [ ] No network calls during import, store, or search
- [ ] Provenance on every stored record
- [ ] `.gitignore` blocks data, secrets, and archives
- [ ] Logs exclude message body content
- [ ] Attachment paths sanitised

---

© EDN Systems
