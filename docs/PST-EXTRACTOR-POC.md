# PST Extractor Proof of Concept

Evaluation record for selecting the Module 001 PST ingestion adapter.

**Status:** Awaiting real probe results. **No adapter selected.**

PoC scripts live under `poc/pst/`. They are disposable and must not be imported
by the production `edn` package.

---

## Candidates

| Option | Approach | Licence |
|--------|----------|---------|
| **A: libpff / pypff** | Direct PST parsing via Python bindings | LGPL |
| **B: readpst (libpst)** | External converter; list or convert to maildir/mbox | GPL |

Outlook COM is **excluded**.

---

## Scoring matrix

Score each criterion **1–5** after real probe results exist. Leave blank until
measured. Higher is better unless noted.

| Criterion | libpff / pypff | readpst | Notes |
|-----------|----------------|---------|-------|
| Windows installation effort | | | 1 = difficult, 5 = straightforward |
| Python 3.14 compatibility | | | Tested interpreter: _TBD_ |
| Source read-only confidence | | | Confidence PST is never modified |
| Folder enumeration | | | |
| Message-count fidelity | | | |
| Sender / recipient / date fidelity | | | |
| Plain-text body availability | | | Metadata-only in first probe |
| HTML body availability | | | Metadata-only in first probe |
| Attachment byte fidelity | | | Not tested in first probe |
| Unicode handling | | | |
| Nested-folder handling | | | |
| Contacts / calendar coverage | | | Out of Module 001 initial scope |
| Performance (representative archive) | | | Record elapsed seconds from JSON |
| Temporary disk use | | | |
| Licensing implications | | | Lower = more concern if noted |
| Maintainability | | | |
| Unattended execution | | | |

---

## Probe artefacts

| Report | Script |
|--------|--------|
| `environment.json` | `python -m poc.pst.inspect_environment` |
| `probe_libpff.json` | `python -m poc.pst.probe_libpff` |
| `probe_readpst.json` | `python -m poc.pst.probe_readpst` |
| `comparison.json` | `python -m poc.pst.compare_results` |

---

## Decision

| Field | Value |
|-------|-------|
| Selected adapter | _Pending_ |
| Decision date | _Pending_ |
| Operator approval | _Pending_ |
| Rationale | _Pending real results_ |

---

© EDN Systems
