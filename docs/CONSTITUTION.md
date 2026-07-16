# EDN OS Constitution

> **Knowledge Compounds.**

This document defines the non-negotiable principles governing EDN OS design and implementation. Development sprints may schedule work, but they do not define architecture. These rules do not.

---

## Purpose

EDN OS is the operating system for EDN Systems. It captures organisational knowledge once, makes it searchable, reduces administration, and improves decision quality — building systems that compound over time.

---

## Core Principles

| Principle | Meaning |
|-----------|---------|
| **Knowledge Compounds** | Every captured record increases the value of the whole. Favour durable structure, provenance, and reuse over one-off scripts. |
| **Local-first** | Primary data and indexes live on the operator's machine. Network and cloud services are optional extensions, never prerequisites. |
| **Read-only by default** | Source systems and archives are never modified. Writes are limited to local derived stores under EDN OS control. |
| **AI assists, humans decide** | AI may summarise, suggest, or rank — but is never the source of truth. Authoritative answers come from stored records with provenance. |
| **Security by design** | Data classification, encryption, and access boundaries are defined before features ship — not retrofitted. |
| **Modular architecture** | Components are small, typed, testable, and composable. New sources plug in without rewriting core logic. |
| **Everything connected** | Records retain provenance to their origin so any extracted item can be traced back to its source. |
| **Foundation discipline** | Shared infrastructure belongs in Foundation (MOD-000) only when at least two durable modules require it, or when it is essential platform governance. Foundation must remain small and must not become a miscellaneous utilities layer. |
| **Module map discipline** | Module maps express ownership and dependency direction. Candidate modules do not authorise implementation and may be revised as evidence accumulates. |

---

## Data Sovereignty

- Runtime data resides under an **approved encrypted data root**. `E:\EDN OS` is the production default (defined by Foundation).
- A path beginning with `E:\` is **not** proof of encryption. Operators are responsible for encryption at the volume level. Encryption verification is not required in the initial implementation.
- Synthetic unit tests may use temporary local directories outside the production data root.
- The Git repository contains **code and documentation only**. Code remains outside the data root.
- The following must **never** be committed: PST files, extracted attachments, SQLite databases, search indexes, runtime logs, credentials, secrets, import reports, and local configuration.

---

## Source Integrity

- Original archives (e.g. Outlook PST files) are opened **read-only** and **never modified**.
- Every extracted record must retain provenance linking it to:
  - a registered `source_archive` (path and fingerprint),
  - the `import_run` that processed it,
  - an adapter-generated `source_record_key` unique within the archive,
  - folder path within the archive.

---

## AI Boundaries

- Memory (MOD-001, initial implementation): **no source email content** (body, headers, attachments, or derived text) may be sent to cloud AI services.
- Future AI integration requires explicit human approval before any external action (upload, API call, or sync).
- Derived AI outputs, when introduced, must reference source record IDs — not replace them.

---

## Engineering Standards

- Python modules use **type annotations** throughout.
- Every module must be **unit-testable** without live source data.
- Prefer **composition over inheritance**.
- Do not duplicate functionality across modules.
- Build the **smallest useful working version** first; expand only when a module specification explicitly requires it.
- Architectural decisions outside documented module scope require **human approval** before implementation.
- Components depend on **domain contracts**, not one another's concrete implementations.
- Feature modules depend on Foundation; Foundation must never depend on feature modules.

---

## Development Sprints

Short implementation sprints deliver work against module specifications. Sprints:

- schedule, prioritise, and track implementation tasks;
- do **not** define software architecture, module boundaries, or security controls.

Architecture is defined only in `CONSTITUTION.md`, `ARCHITECTURE.md`, `SECURITY.md`,
`MODULE-MAP.md`, and `MODULE-NNN-*.md` documents.

---

## Extensibility (Future Modules)

Architecture must remain modular enough to later support:

- Microsoft 365
- SharePoint
- Home Assistant
- Voice interfaces
- Personal data vaults

These integrations are not designed or built until a future module specification authorises them.

---

## Document Hierarchy

| Document | Role |
|----------|------|
| `CONSTITUTION.md` | Immutable principles (this file) |
| `ARCHITECTURE.md` | System structure and component contracts |
| `MODULE-MAP.md` | Module catalogue, ownership, and dependency direction |
| `SECURITY.md` | Threat model, controls, and data-handling rules |
| `MODULE-000-FOUNDATION.md` | Platform foundation specification |
| `MODULE-NNN-*.md` | Durable feature module specifications |

When documents conflict, the Constitution takes precedence.

---

© EDN Systems
