# EDN OS Security Model

Security requirements and controls for EDN OS. Applies platform-wide.

| Marker | Scope |
|--------|-------|
| **F000** | Foundation (MOD-000) |
| **M001** | Memory (MOD-001) initial implementation |

---

## Division of Responsibility

| Layer | Defines | Applies to |
|-------|---------|------------|
| **Foundation** | Platform-wide path policy, configuration rules, logging rules, secret-handling rules, repository hygiene | All modules |
| **Memory** | PST archive handling, extracted email content, provenance, sensitivity defaults, import/search offline constraints | MOD-001 only |

Foundation introduces **no network access and no cloud services**. Memory inherits Foundation rules and adds domain-specific controls.

Real local settings remain at `E:\EDN OS\Configuration\` — outside Git.

---

## Threat Model

| Threat | Impact | Control |
|--------|--------|---------|
| Secrets in Git | Credential leak | Code and docs only in Git; config on data root **(F000)** |
| Unencrypted data at rest | Exposure if device lost | Approved encrypted data-root policy; `E:\EDN OS` default **(F000)** |
| Sensitive content in logs | Confidential disclosure | Foundation logging: no record bodies or credentials **(F000)** |
| Source archive tampering | Loss of provenance trust | Read-only PST access; fingerprint at registration **(M001)** |
| Data exfiltration to cloud AI | Email disclosure | No source content to cloud AI **(M001)** |
| Duplicate/orphan records | Incorrect search | Provenance + idempotent import **(M001)** |
| Unauthorized write-back | Unintended external action | Read-only by default **(M001)** |
| Unreviewed sensitive content | Inappropriate reuse | `SensitivityStatus.unreviewed` default **(M001)** |

---

## Data Root Policy (Foundation)

| Rule | Detail |
|------|--------|
| Production default | `E:\EDN OS` |
| Encryption expectation | Operators use an encrypted volume; EDN OS does not verify encryption in initial implementation |
| Path is not proof | `E:\` prefix does not demonstrate encryption |
| Test exception | Synthetic unit tests may use temporary local directories |
| Code separation | Application code in Git repository, outside data root |

---

## Data Classification

| Class | Examples | Storage | Git |
|-------|----------|---------|-----|
| **Source** | PST archives | `E:\EDN OS\Source\PST\` | Never |
| **Derived** | Extracted bodies, attachments | `E:\EDN OS\Data\` | Never |
| **Index** | SQLite DB, FTS5 | `E:\EDN OS\Data\Databases\` | Never |
| **Operational** | Logs, import reports | `E:\EDN OS\Logs\`, `Exports\` | Never |
| **Configuration** | Local settings | `E:\EDN OS\Configuration\` | Never |
| **Secret** | API keys, tokens | `Configuration\` or OS store | Never |
| **Code** | Python modules, tests | Git repository | Yes |
| **Documentation** | Architecture, module specs | Git repository | Yes |

---

## Foundation Controls (F000)

| Area | Rule |
|------|------|
| Configuration | Example config in Git; real config excluded; validation fails fast |
| Logging | Human-readable operational logs under `Logs\`; no sensitive record content |
| Network | No network access in Foundation initial implementation |
| Cloud | No cloud services in Foundation initial implementation |
| Repository | Git contains code and documentation only |
| Secrets | Never in source code, tests, or committed config |

---

## Memory Controls (M001)

### Source handling

| Rule | Detail |
|------|--------|
| Read-only access | PST opened read-only; no create, update, or delete on source |
| No relocation | EDN OS does not move or rename operator PST files |
| Fingerprinting | SHA-256 via Foundation `fingerprint_file`; stored on `source_archives` |
| Provenance | Messages reference `source_archive_id` and `import_run_id`; search resolves full provenance |

### Sensitivity

| Rule | Detail |
|------|--------|
| Default | All imported former-employer content: `unreviewed` |
| Values | `unreviewed`, `private_reference`, `potentially_reusable`, `restricted`, `quarantined` |
| Classification | No automated sensitivity classification in initial implementation |
| Quarantine | `quarantined` records excluded from routine search |

### AI and external services

| Rule | Detail |
|------|--------|
| No cloud upload | No message bodies, headers, metadata, or attachment content to external AI |
| No network dependency | Import, store, and search fully offline |
| AI is not authoritative | Future AI outputs reference record IDs; stored records remain source of truth |

### Human approval gate (future)

Any transmission outside the local data root requires explicit operator initiation, disclosure, and confirmed approval. Not built in initial implementation.

---

## Repository Hygiene (Foundation)

Must never be committed:

- `*.pst` and other mail archives
- Extracted attachments, SQLite databases, index files
- Runtime logs, import reports
- `.env`, credentials, API keys, tokens
- Contents of `E:\EDN OS\` data directories

A `.gitignore` must enforce these before the first application commit.

---

## Input Validation (Memory)

- Source paths validated (exist, readable, `.pst` extension for PST ingest).
- Search queries parameterised through SQLite.
- Attachment filenames sanitised; path traversal prevented.

---

## Security Checklists

### Foundation (F000)

- [ ] Example configuration committed; local configuration excluded
- [ ] Logging excludes sensitive record content
- [ ] No network calls in Foundation
- [ ] Data-root policy documented and validated via configuration
- [ ] `.gitignore` blocks data, secrets, and archives

### Memory (M001)

- [ ] PST opened read-only only
- [ ] Production data root `E:\EDN OS` (or approved encrypted equivalent)
- [ ] No network calls during import, store, or search
- [ ] Provenance resolved for every search result
- [ ] Imported content defaults to `unreviewed`
- [ ] Logs and reports exclude message body content
- [ ] Attachment paths sanitised

---

© EDN Systems
