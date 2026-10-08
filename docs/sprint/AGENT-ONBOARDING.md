# Dot and Grok October onboarding

Use GitHub issues, current main, commits, PR evidence and repository documents as the shared control plane. No ChatGPT/Grok history is required. Accepted baseline merge: `c85938c44ef230b5e4574b084d709f263b92adc0`; see OCTOBER-BASELINE.md.

## Start independently

Clone the repository with your already-approved repository identity. Confirm `git merge-base --is-ancestor c85938c44ef230b5e4574b084d709f263b92adc0 origin/main` succeeds. Create your own checkout and issue branch from current main; record actual base SHA. Do not share working copies, runtime stores, tokens or agent memory. Read AGENTS.md, CURRENT_STATE.md, SECURITY.md, Constitution, architecture/data/integration documents, MULTI_AGENT_WORKFLOW.md and your issue before editing.

Linux Python 3.11/3.12 is the supported full-suite validation environment. Install `.[dev]` in an isolated environment; run pytest, Ruff, native mypy, `python tools/ci/check_integrity.py` and full PR-range `git diff --check`. On Windows run full pytest to JUnit and `python tools/ci/check_windows_baseline.py <report.xml>`; retain all failure evidence. Native Windows mypy and IMS/Pester limitations are documented in OCTOBER-BASELINE.md. All data must be synthetic and temporary. CI needs no live credentials.

## Roles and first handover

Dot: refine bounded acceptance, identify overlapping files and dependencies, check architecture/security, independently review Grok's exact PR head, and escalate owner decisions. Dot may implement only with a different reviewer. No self-approval.

Grok: implement one ready issue, claim it in GitHub before editing, use an isolated `feature/oct-<ticket>-<slug>` or `docs/oct-<ticket>-<slug>` branch, add meaningful tests/docs, open a draft PR to main and fix review findings. Do not start a blocked issue or expand its authority.

Elliot: selects priority, confirms claims/account access, resolves consequential scope/security/architecture conflicts and explicitly approves each merge/release. Role names are not GitHub account assignments. No new GitHub/Microsoft permissions or Global Admin access are granted by these documents.

Start with issue #4 for enforcement documentation or issue #5 for the Operations acceptance pack. These are ready for claim; Grok has not been launched or assigned an account. Dot-authored onboarding PR must be independently reviewed. Issue #7 is an implementation option after Dot confirms scope/dependencies. Do not run two storage/schema issues concurrently when files overlap.

## Durable claim and review messages

Claim: issue ID; implementer identity; reviewer identity; base SHA; branch; overlapping files; allowed scope; acceptance checklist; dependencies/owner decisions; next update.

Handover: issue/PR URL; base/head SHAs; resulting behavior; synthetic checks and baseline comparison; findings fixed/unresolved; documentation/rollback; remaining limits; requested owner decision. Never paste customer/source data or credentials into the public repository.

Review: exact head SHA; acceptance/provenance/security/replay/compatibility findings with file/line evidence; required gates; independent-review identity; GO/HOLD limited to technical scope. The PR's review approval does not grant merge authority.

## Boundaries and recovery

Development is synthetic/local. Staging is not established and requires separate approval of environment, data and identities. Production and source reads are independently gated. Excluded UWC assets, expired grants and historical live packs confer no current authority. No bot-to-bot API, background orchestrator or automatic deployment is introduced.

Serialize overlapping files. Never force-push, overwrite another branch or silently resolve conflicting contracts. Record alternatives in the issue; Dot resolves routine interpretation, Elliot decides security/architecture/persistent disagreement. If an agent stops, leave last SHA/checks/claim status and reassign explicitly in the same issue. End-of-month evaluation uses accepted increments, rework, regressions, owner effort, blocked time and agent/tool cost; no monitor or reminder is created.
