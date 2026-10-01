# Decision register

This register indexes evidence and distinguishes established constraints from October proposals. It does not manufacture historical approvals. Elliot approves changes outside existing scope.

| ID | Status | Decision and reason | Evidence |
|---|---|---|---|
| D-01 | Established principle | Local-first, provenance, read-only defaults, AI assists/humans decide | docs/CONSTITUTION.md, docs/SECURITY.md |
| D-02 | Implemented | Retain Python/SQLite/Streamlit; add Operations as an isolated store rather than replace Memory | operations/storage.py, docs/OPERATIONS-V1.md |
| D-03 | Implemented | Event identity is source/account/native ID; replay preserves first content | EventStore.insert, tests/operations/test_events.py |
| D-04 | Implemented | Legacy Outlook metadata contract stays distinct from explicit Operations body intake | operations/outlook.py, connectors/microsoft_outlook/client.py |
| D-05 | Implemented constraint | Permission-first governed evidence, domain isolation, opaque provider IDs distinct from authority | core/security.py, core/references.py, docs/OPAQUE-RESOURCE-IDENTITY-REPAIR.md |
| D-06 | Established boundary | Proposal approval never implies external execution; provider/delegation gates independent | IC-012, IC-DEV-003, PA-009 documents |
| D-07 | Active scope | Operations Inbox and small useful increments; deeper graph/UWC/cloud triage expansion frozen | docs/NOW.md |
| D-08 | October proposal | Dot leads/specifies/reviews; Grok implements; Elliot sets priorities/approves merges and consequential changes | User sprint request; MULTI_AGENT_WORKFLOW.md |
| D-09 | October proposal | One issue, one assigned implementer, isolated branch/checkout, independent review and exact-commit CI | MULTI_AGENT_WORKFLOW.md; OCT-01/OCT-02 |
| D-10 | Open owner decision | Select integration base and merge sequence; main is 157 commits behind inspected code | CURRENT_STATE.md; OCT-01 |
| D-11 | Open owner decision | Operations real runtime path, encryption/access evidence and live-read acceptance scope | SECURITY.md; OCT-03 |
| D-12 | Open documentation decision | Reconcile legacy Memory schema, module IDs and composition rules with implemented code | CURRENT_STATE.md; OCT-09 |

Detailed IMS decisions remain in [IMS decision log](docs/ims/EDN-IMS-Decision-Log.md), architecture reviews and owner packs. These records have their own dates/scope. Do not reinterpret dated decisions as permission for a new October deployment.

For a significant new decision, record date, owner, status (proposed/accepted/superseded), exact scope, alternatives, rationale, security/data impact, compatibility, acceptance/rollback and linked issue/PR. An accepted entry needs owner evidence. Rejected alternatives should explain a real tradeoff, not create speculative architecture. When superseding an entry, retain its history and link the successor.
