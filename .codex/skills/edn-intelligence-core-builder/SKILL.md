---
name: edn-intelligence-core-builder
description: Continue EDN Intelligence Core development from repository-owned state, roadmap, architecture, and standing-authority policy. Use when planning, implementing, repairing, reviewing, or resuming an Intelligence Core increment, especially in a fresh Codex session that must reconstruct current progress and stop at genuine owner-authority boundaries.
---

# EDN Intelligence Core Builder

Continue routine development autonomously while treating repository artifacts—not chat history—as the source of truth.

## Reconstruct the project

1. Work from the EDN OS repository root.
2. Read `config/intelligence-core-development-state.json` completely.
3. Read `config/development-authority-policy.json` and `config/intelligence-core-roadmap.json` completely.
4. Read every architecture document referenced by the development state that is relevant to the selected increment.
5. Inspect the current branch, commit, working tree, and tests. Preserve every pre-existing change.
6. Compare the observed repository with the expected branch, commit, and known dirty paths. Stop on unexpected repository state.

## Select work

- Select only a pending task whose prerequisites are complete.
- Prefer `next_recommended_increment` when eligible.
- Evaluate every declared action against the authority policy before implementation.
- Treat allowed development actions as standing authority, not as authority for live or external operations.
- If a task is owner-blocked, record the structured escalation and select another eligible routine task when one exists.
- Fail closed for unknown or ambiguous authority.

## Execute the bounded loop

1. State the selected task and its acceptance criteria.
2. Make the smallest architecture-consistent plan.
3. Implement within the task's expected components and declared authority.
4. Run the task's required checks using synthetic or already-authorised local development data.
5. Review architecture, authority, security, regression risk, scope, tests, documentation, and state accuracy.
6. Repair routine findings and retest, subject to the configured repair limit.
7. Stop on repeated identical failure, elapsed/task limits, unexpected repository changes, or material architecture conflict.
8. On success, update deterministic development state and documentation and record decision/outcome audit events. If the Git checkpoint policy passes, stage only the completed increment, commit with its matching message, push only the current feature branch to its existing upstream, verify equality, and record the checkpoint. Otherwise prepare—but do not create—a commit.
9. Continue only while another eligible task fits the run budget and standing authority.

Never store chain-of-thought. Store task IDs, decisions, reason codes, evidence references, validation outcomes, and timestamps only.

## Escalate concisely

Escalate only genuine owner boundaries. Include:

- what is blocked;
- why owner authority is required;
- the exact minimum request;
- effects of approval and decline;
- reversibility;
- the recommended `GO`, `NO-GO`, or `CONDITIONAL GO` response.

Owner authority is required for new data access, scope expansion, external permissions or authentication, production mutation, external communication, financial/legal actions, destructive or irreversible work, material architecture changes, weakened security, changed human-authority boundaries or product vision, material new cost, protected-branch integration, and indeterminate cases.

Do not turn ordinary implementation uncertainty into owner escalation.

## Safety boundaries

- Do not access live services or protected evidence unless a separate, current approval expressly authorises the exact operation.
- Do not infer authority from installed capability.
- Do not weaken checks or broaden scope to obtain a passing result.
- Do not discard, overwrite, broadly stage, merge, rebase, force-push, rewrite history, change remotes/upstreams, or deploy. A normal push is routine only when `evaluate_git_checkpoint` authorises the exact validated feature-branch checkpoint.
- Keep implementation and review conceptually separate even when one Codex session performs both roles.
- Use `src/edn/development/agent.py` as the development-agent boundary; do not introduce undocumented or cloud dependencies.

## Finish

Report the task result, validation evidence, review outcome, state changes, prepared commit message, remaining limitations, and any structured owner escalation. A fresh session must be able to resume from the repository alone.
