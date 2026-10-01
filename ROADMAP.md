# October 2026 development roadmap

Objective: make EDN OS independently understandable and safely advance the Operations Inbox using Dot as technical lead/reviewer and Grok as implementer. Preserve `docs/NOW.md` scope. This is a proposed sequence; Elliot chooses priority and approves gated changes. See [scoped tickets](docs/sprint/OCTOBER-2026-TICKETS.md).

| Window (Sydney) | Delivery focus | Exit evidence |
|---|---|---|
| 1–7 October | OCT-01 baseline reconciliation, OCT-02 reproducible Linux checks; prepare OCT-03 storage/live acceptance pack | Agreed base/branch graph, portable handover, exact-commit synthetic results, documented owner gates |
| 8–14 October | OCT-04 synthetic SharePoint job-request Events; OCT-05 local triage | Source contract/replay tests; triage persists without source mutation |
| 15–21 October | OCT-06 import coverage visibility; OCT-07 synthetic backup/restore | Incomplete intake visible; restart/replay safe; recovery demonstrated |
| 22–28 October | OCT-08 unsupported-platform handling; OCT-09 architecture/doc reconciliation | Protection stays fail-closed; schema/layout/ownership docs match evidence |
| 29–31 October | Fix review findings and evaluate experiment | Accepted tickets, residual risk, owner effort/spend/rework and next-month recommendation |

OCT-04 depends on repository-only inspection of the separate website contract; the task must be reduced or blocked if its fields are unavailable. OCT-05 must not mix triage with source mutation. Backup/restore and OS changes cannot weaken protected-store controls. No production activation, new tenant permission, cloud triage, finance/CRM catalogue, deeper graph, Power Apps/Power Automate expansion or external executor is included.

Readiness gates: baseline selected -> reproducible Linux validation -> independent review -> Elliot-approved merge. Any real source-read acceptance requires a separate current scope/identity/path decision and isolated environment. Release additionally needs explicit production authority and rollback evidence. A passing synthetic sprint does not remove those gates.

At month end, compare outcomes with the initial baseline: accepted useful increments, review defects caught, escaped regressions, owner minutes and cost per accepted ticket, blocked work and each agent's strongest tasks. Elliot can retain both roles, reassign responsibilities or consolidate based on recorded evidence. Do not score speed without regression and authority compliance.
