# EDN OS Security Model

Security requirements and controls for EDN OS. Applies platform-wide. Module 001 initial-implementation controls are marked **M001**.

---

## Threat Model (Module 001)

| Threat | Impact | Control |
|--------|--------|---------|
| Source archive tampering | Loss of trust in provenance | Read-only PST access; fingerprint at registration **(M001)** |
| Data exfiltration to cloud AI | Confidential email disclosure | No source content sent to cloud AI in the initial implementation **(M001)** |
| Secrets in Git | Credential leak | Repository contains code and docs only; secrets under data root **(M001)** |
| Unencrypted data at rest | Exposure if device lost | Approved encrypted data root policy; `E:\EDN OS` production default **(M001)** |
| Duplicate/orphan records | Incorrect search results | Provenance via `source_archives` + `source_record_key`; idempotent import **(M001)** |
| Unauthorized write-back | Unintended external action | Read-only by default; human approval gate for future actions **(M001)** |
| Unreviewed sensitive content | Inappropriate reuse of former-employer data | `sensitivity_status` defaults to `unreviewed`; no automated classification **(M001)** |

---

## Data Root Policy

| Rule | Detail |
|------|--------|
| Production default | `E:\EDN OS` |
| Encryption expectation | Operators must use an encrypted volume. EDN OS does not verify encryption in the initial implementation |
| Path is not proof | A path beginning with `E:\` does not demonstrate encryption |
| Test exception | Synthetic unit tests may use temporary local directories |
| Code separation | Application code remains in the Git repository, outside the data root |

---

## Data Classification

| Class | Examples | Storage | Git |
|-------|----------|---------|-----|
| **Source** | PST archives | `E:\EDN OS\Source\PST\` | Never |
| **Derived** | Extracted bodies, attachments | `E:\EDN OS\Data\` | Never |
| **Index** | SQLite DB, FTS5 tables | `E:\EDN OS\Data\Databases\` | Never |
| **Operational** | Import logs, import reports | `E:\EDN OS\Logs\`, `E:\EDN OS\Exports\` | Never |
| **Configuration** | Local settings | `E:\EDN OS\Configuration\` | Never |
| **Secret** | API keys, passwords, tokens | `Configuration\` or OS credential store | Never |
| **Code** | Python modules, tests | Git repository | Yes |
| **Documentation** | Architecture and module docs | Git repository | Yes |

---

## Storage Rules

1. Runtime data resides under the configured encrypted data root (`E:\EDN OS` in production).
2. Attachment files are written with restrictive permissions (owner read/write only where the OS supports it).
3. Configuration and secrets are never committed to Git.

---

## Source Handling

| Rule | Detail |
|------|--------|
| Read-only access | PST files opened in read-only mode; no create, update, or delete on source |
| No relocation | EDN OS does not move or rename operator PST files |
| Fingerprinting | SHA-256 hash computed at registration; stored on `source_archives` |
| Provenance | Messages reference `source_archive_id` and `import_run_id`; search resolves full provenance |

---

## Sensitivity (Module 001)

| Rule | Detail |
|------|--------|
| Default status | All imported former-employer content: `unreviewed` |
| Allowed values | `unreviewed`, `private_reference`, `potentially_reusable`, `restricted`, `quarantined` |
| Classification | No automated sensitivity classification in Module 001 |
| Quarantine | Records marked `quarantined` are excluded from routine search (implementation detail) |

---

## AI and External Services (Module 001)

| Rule | Detail |
|------|--------|
| No cloud upload | Message bodies, headers, metadata, and attachment content must not be transmitted to external AI services |
| No network dependency | Import, store, and search operate fully offline |
| AI is not authoritative | When AI is introduced in future modules, outputs reference record IDs; stored records remain the source of truth |

---

## Human Approval Gate (Future)

Any action that transmits data outside the local data root boundary requires:

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
- Runtime logs and import reports
- `.env`, credentials, API keys, tokens
- Contents of `E:\EDN OS\` (Source, Data, Configuration, Logs, Exports, Backups)

A `.gitignore` must enforce these patterns before the first application commit.

---

## Secrets Management

- No secrets in source code, tests, or documentation.
- Local configuration lives in `E:\EDN OS\Configuration\`.
- Settings files are excluded from Git.

---

## Logging

| Rule | Detail |
|------|--------|
| Location | `E:\EDN OS\Logs\` |
| Content | Operational events (import start/end, counts, error summaries); **no message bodies** |
| Import reports | Machine-readable JSON; separate from human-readable logs |
| Retention | Operator-managed; not committed to Git |

---

## Input Validation

- Source paths must be validated (exist, readable, `.pst` extension for Module 001 PST ingest).
- Search queries are parameterised through SQLite — no string-concatenated SQL.
- Attachment filenames are sanitised before writing to disk (path traversal prevention).
- `storage_filename` must differ from `original_filename` when sanitisation alters the name.

---

## Module 001 Security Checklist

- [ ] PST opened read-only only
- [ ] Production data root set to `E:\EDN OS` (or approved encrypted equivalent)
- [ ] No network calls during import, store, or search
- [ ] Provenance resolved for every search result
- [ ] All imported content defaults to `sensitivity_status = unreviewed`
- [ ] `.gitignore` blocks data, secrets, and archives
- [ ] Logs and reports exclude message body content
- [ ] Attachment paths sanitised

---

© EDN Systems
