# Dot, Grok and Elliot development workflow

October 2026 repository development operating agreement. GitHub issues, PRs, commits and repository documents are the shared record. This file defines team behavior; hosted PR CI is established; required-check/review enforcement is manual until Elliot separately approves repository protection settings. No provider-specific memory is required.

## Ownership

| Role | Responsibility | Authority limit |
|---|---|---|
| Elliot | Product priorities, classification/access decisions, architecture exceptions, merge/release approval, escalation | Final human authority |
| Dot | Technical lead: refine issues/acceptance, dependency planning, independent review, regressions and documentation reconciliation | Does not approve its own implementation or infer production authority |
| Grok Bot | Implement one assigned issue, add meaningful tests/docs, provide review evidence and fix findings | No unilateral merge, deployment, permission grant or scope expansion |
| Independent reviewer | Review Dot-authored implementation; Elliot or another designated engineer | Required when Dot becomes implementer |

These are responsibilities, not automatic access grants. If the agents cannot communicate directly, Elliot can relay a GitHub issue/PR reference; decisions still land in the repository. No bot-to-bot API or autonomous runtime orchestrator is needed.

## Issue to PR

1. Elliot selects priority; Dot writes a bounded issue using the template. Include exact base SHA, allowed files/behavior, exclusions, dependencies, acceptance tests, data boundary and rollback. Assign one implementation owner and one reviewer. Record any expiry/owner gates explicitly.
2. Before coding, the implementer records the claim and overlapping files in the issue. A second implementer must pick a different issue or wait. Unknown availability is not an implicit claim.
3. Use one isolated checkout/worktree per agent and issue. From current authoritative main after verifying the accepted merge ancestry, start `feature/oct-<ticket>-<slug>` for behavior or `docs/oct-<ticket>-<slug>` for documentation. No common working copy and no direct main edits. Verify main contains the approved October baseline before starting.
4. Commit small reviewable increments; test the assigned behavior with synthetic fixtures. Update current docs and maintain frozen manifests unchanged unless that exact change is approved. Supply commands, results and base/head SHAs.
5. Open a PR against main. Disclose any additional unmerged stack separately; ordinary new issues start from main, not an old feature stack.
6. Dot reviews acceptance, source/provenance, policy/error paths, replay, data compatibility, docs and rollback. Review must concern the current head SHA. Author fixes findings; review and required checks repeat after relevant changes. No self-approval.
7. Merge is allowed only after current required checks, independent review, resolved findings and Elliot's explicit merge approval. Elliot/designated authorized maintainer performs the merge. Until protection is configured, enforce this manually; written policy alone is not technical enforcement.

Issue states: proposed -> ready -> claimed -> in progress -> review -> accepted/merged. Add blocked with reason, owner and next decision when needed. Never close as done based on an agent's assertion alone. Existing historical delegated-authority mechanisms have independent restrictions and do not authorize this workflow's merge/rebase/push steps by themselves.

## Validation and CI

The merged `.github/workflows/pr-checks.yml` runs full Linux Python 3.11/3.12 pytest, Ruff, strict native Linux types, frozen/config integrity, full PR-range whitespace and clean-tree checks. Windows Python 3.12 runs all tests and the exact baseline guard. Read-only repository token, no checkout credentials, no live data and no automatic deployment. Actual hosted checks are `Linux synthetic validation (3.11)`, `Linux synthetic validation (3.12)` and `Windows baseline regression guard`; all passed for the accepted successor. IMS PowerShell/Pester checks remain separate.

Issue #4 tracks the repository protection proposal. Until a settings change is separately approved and verified, Elliot manually enforces current-head checks, independent review and explicit merge approval. Agent roles do not grant accounts or privileges.

Windows has 92 baseline failures; preserve a machine-readable identity comparison on each relevant change. No new failures are acceptable. A known Windows baseline does not permit a failing Linux release gate. Linux-targeted type checking is not runtime acceptance. Do not suppress security tests to achieve green.

## Development, staging and production

Development: synthetic source clients/data, temporary stores, localhost UI. Staging: not established by this audit; requires Elliot's approved isolated environment, dataset, identity and source scopes before use. Production: real mail/data/stores, deployed apps, Microsoft tenant and website service. Never share test/production DBs or tokens. No automatic deployment on merge is proposed.

Promotion requires the exact candidate SHA, successful required checks, approved bounded staging acceptance, backup/restore evidence for affected data, rollback plan and separate Elliot release authority. No live source access or Global Admin is granted to either bot. OCT-03 prepares a reviewable live-read plan; it does not execute it.

## Conflicts and escalation

- Compare claimed files before work; serialize shared schemas/configs/manifests. If another PR changes the same contract, pause the overlapping edits and agree an order with Dot.
- Never overwrite/force-push another branch. Bring the agreed target into the feature branch only within applicable Git authority; review each conflict semantically and rerun affected checks. Protected delegation forbids rebase/merge unless separate authority exists.
- Record disagreements as alternatives with evidence/acceptance consequences in the issue. Dot handles routine scope interpretation; Elliot resolves architecture, security, priorities or persistent disagreement. Neither agent gets a unilateral veto through private chat history.
- Stop dependent work for classification uncertainty, new credentials/permissions, runtime data exposure, production mutation, failing protection controls or scope drift. Report facts, bounded proposal and rollback to Elliot; continue unrelated synthetic work.
- If an agent disappears, leave last commit, remaining acceptance checks, no-secret reproduction steps and claim status. Reassign explicitly, using the same issue and a new checkout. Do not restart from conversation memory.

## Definition of done and October evaluation

Done means acceptance behavior demonstrated, no new regressions, required checks on current SHA, independent review, docs current, rollback understood and owner merge approval recorded. Live acceptance is a separate status. Track accepted tickets, cycle time, Elliot minutes per ticket, review defects/rework, regressions, blocked time, agent/tool spend and autonomous completion within scope. Review weekly on 8, 15, 22 and 29 October; final evaluation on 31 October (Sydney dates). No reminder or automation was created.

October baseline is accepted on main. See docs/sprint/OCTOBER-BASELINE.md for exact SHAs and retained limitations.

## Exact-candidate validation handover

Use the SHA in the repair delivery report, never a moving branch name as evidence.
Required workflow check names are `Linux synthetic validation (3.11)`,
`Linux synthetic validation (3.12)` and `Windows baseline regression guard`.
These names are confirmed by hosted jobs. Configuring protection/settings changes
require Elliot's separate authority. Linux requires zero failures and no broad
security skips. Windows runs every Python test, then matches only the 92 audited
identities/signatures and the one known skip; resolved failures are allowed and
new failures/skips/errors/missing baseline cases or collection shrinkage fail.
Do not introduce source credentials. IMS Pester checks remain separate for IMS
changes and require an offline environment with the command surface needed for
mocking; missing PnP commands are environmental failures, not tenant access.
See docs/sprint/OCTOBER-BASELINE.md for accepted hosted results; PREPROMOTION-REPAIRS.md remains historical evidence.
