# EDN OS

> Build the world's best operating system for specialist engineering consultancies.

---

## Vision

EDN OS is the digital operating system for EDN Systems.

It captures knowledge, automates administration, improves decision making and helps engineering businesses scale without losing organisational intelligence.

---

## Mission

- Capture knowledge once.
- Search everything instantly.
- Reduce administration.
- Increase decision quality.
- Build systems that compound over time.

---

## Current Status

### Module 000 — Foundation

Architecture definition in progress.

### Module 001 — Memory

Architecture approved; implementation follows Foundation.

Initial implementation objectives (Outlook PST archives):

- [ ] Register source archive and verify PST fingerprint
- [ ] Complete PST extractor proof of concept (libpff vs readpst)
- [ ] Select the ingestion adapter (validate Python version compatibility)
- [ ] Import message metadata, participants, and bodies
- [ ] Extract and catalogue attachments with full metadata
- [ ] Store records in SQLite under `E:\EDN OS`
- [ ] Implement SQLite FTS5 keyword search with resolved provenance
- [ ] Handle partial failures and produce machine-readable import reports

Development sprints may be used to schedule work, but modules define the durable product architecture.

---

## Design Principles

- Local-first
- AI assists, humans decide
- Read-only by default
- Security by design
- Modular architecture
- Everything connected

---

## Long-Term Goal

Create the world's best AI-powered operating system for specialist engineering consultancies.

---

© EDN Systems
