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

### Module 004 — Work

Universal Work Capture V1 has a repository-complete, synthetic implementation.
It defines one human-fact event owned operationally by the existing SharePoint
Work Log, project defaults, secure evidence/photo rules, append-only corrections
and deterministic downstream projections. Live Microsoft activation remains a
separate owner-authority gate.

See [Module 004 — Work](docs/MODULE-004-WORK.md) and the
[Universal Work Capture V1 design](docs/work-capture/UNIVERSAL-WORK-CAPTURE-V1.md).

Development sprints may be used to schedule work, but modules define the durable product architecture.

---

## Architecture

EDN OS is organised as numbered durable modules (MOD-000 through MOD-012).
Approved modules have specifications; candidate modules guide long-term ownership
only.

See [Module Map](docs/MODULE-MAP.md) for the full catalogue, ownership definitions,
and dependency rules.

---


## Local Email Search Interface

The first EDN OS browser interface searches an existing email-memory database
entirely on the local machine. It is read-only and does not create a database
when the configured path is missing.

While a production import is actively writing, wait for it to finish before
launching the interface against that database.

```bash
source /home/elliot/.venvs/edn-os/bin/activate
cd /home/elliot/projects/edn-os

export EDN_MEMORY_DB="/mnt/f/EDN OS/Database/edn-memory.db"

streamlit run src/edn/ui/app.py \
  --server.address 127.0.0.1 \
  --browser.gatherUsageStats false
```

Open [http://localhost:8501](http://localhost:8501) if the browser does not
open automatically.

`EDN_MEMORY_DB` is required and must identify an existing, initialized EDN
email-memory SQLite database. The application binds only to localhost. The
`--browser.gatherUsageStats false` option disables Streamlit usage statistics.
Email bodies are rendered only as plain text and remain collapsed by default.

For local development, create a synthetic database rather than copying
production email data into the repository:

```bash
python -m edn.memory.cli init /tmp/edn-memory-dev.db
export EDN_MEMORY_DB=/tmp/edn-memory-dev.db

streamlit run src/edn/ui/app.py \
  --server.address 127.0.0.1 \
  --browser.gatherUsageStats false
```

---

## Ask EDN

The browser UI also includes grounded email question answering. Ask EDN safely
converts natural-language questions into local FTS5 retrieval, produces a local
extractive answer, and validates every numbered source citation. No cloud AI or
external API is used.

Set `EDN_LLM_PROVIDER=extractive` (the default) to enable local answers, or set
`EDN_LLM_PROVIDER=disabled` to disable answer generation entirely.

See [Module 002.3 — Ask EDN](docs/MODULE-002-ASK-EDN.md) for retrieval,
citation, privacy, configuration and limitation details.

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
