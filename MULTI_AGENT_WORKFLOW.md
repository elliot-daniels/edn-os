# Dot, Grok and Elliot development workflow

Proposed October 2026 operating agreement. GitHub issues, PRs, commits and repository documents are the shared record. This file defines team behavior; branch protection and CI are not yet established on the inspected implementation. No provider-specific memory is required.

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
3. Use one isolated checkout/worktree per agent and issue. After OCT-01 chooses the integration base, start `feature/oct-<ticket>-<slug>` for behavior or `docs/oct-<ticket>-<slug>` for documentation. No common working copy and no direct main edits. Do not start from remote main blindly.
4. Commit small reviewable increments; test the assigned behavior with synthetic fixtures. Update current docs and maintain frozen manifests unchanged unless that exact change is approved. Supply commands, results and base/head SHAs.
5. Open a PR against the agreed integration target. A docs-only PR may still inherit substantial unmerged feature history: disclose that explicitly. Separate stack review from feature approval; never treat the full range as a routine documentation merge.
6. Dot reviews acceptance, source/provenance, policy/error paths, replay, data compatibility, docs and rollback. Review must concern the current head SHA. Author fixes findings; review and required checks repeat after relevant changes. No self-approval.
7. Merge is allowed only after current required checks, independent review, resolved findings and Elliot's explicit merge approval. Elliot/designated authorized maintainer performs the merge. Until protection is configured, enforce this manually; written policy alone is not technical enforcement.

Issue states: proposed -> ready -> claimed -> in progress -> review -> accepted/merged. Add blocked with reason, owner and next decision when needed. Never close as done based on an agent's assertion alone. Existing historical delegated-authority mechanisms have independent restrictions and do not authorize this workflow's merge/rebase/push steps by themselves.

## Validation and CI

OCT-02 proposes a Linux PR workflow for the agreed integration target: install `.[dev]`, full pytest with JUnit, Ruff, strict mypy, relevant config/frozen-manifest integrity checks and whitespace validation. Use read-only repository permissions, no source credentials, no live APIs or real datasets. Avoid exposing private artifacts. Treat PowerShell/Pester tests separately for installer changes.

Current `chore/uwc-linux-validation` workflow triggers only for its own branch/manual dispatch. It is not an all-PR required check. The audited Operations base had no CI workflow. The repair candidate adds `.github/workflows/pr-checks.yml` for all PR targets, merge-group and manual execution; it has not run on GitHub. Branch protection, reviewer enforcement and staging availability are unverified; OCT-02's report must state what was actually configured versus merely recommended.

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

Pre-promotion status: HOLD. Proposed PR checks and reconciled authority state are prepared locally; original 48d902e remains unchanged and has not been promoted. See [authority reconciliation](docs/sprint/AUTHORITY-RECONCILIATION.md).

## Exact-candidate validation handover

Use the SHA in the repair delivery report, never a moving branch name as evidence.
Proposed required checks are `Linux synthetic validation (3.11)`,
`Linux synthetic validation (3.12)` and `Windows baseline regression guard`.
Confirm their actual hosted names before configuring protection; settings changes
require Elliot's separate authority. Linux requires zero failures and no broad
security skips. Windows runs every Python test, then matches only the 92 audited
identities/signatures and the one known skip; resolved failures are allowed and
new failures/skips/errors/missing baseline cases or collection shrinkage fail.
Do not introduce source credentials. IMS Pester checks remain separate for IMS
changes and require an offline environment with the command surface needed for
mocking; missing PnP commands are environmental failures, not tenant access.
See docs/sprint/PREPROMOTION-REPAIRS.md for exact local results and remaining gates.
