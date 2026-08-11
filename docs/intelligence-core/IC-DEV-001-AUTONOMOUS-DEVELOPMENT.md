# IC-DEV-001 — Autonomous Development Orchestrator

## Purpose

IC-DEV-001 adds a narrow, deterministic control plane for continuing EDN Intelligence Core development. It moves routine planning, implementation, validation, repair, review, documentation, and state updates under standing authority while reserving genuine business and external-effect decisions for the owner.

It is development-only. It does not authenticate, contact external services, mutate production systems, deploy, merge, push, or grant itself authority.

## Architecture

```text
Owner vision and exception decisions
                 |
                 v
Development authority policy ---- Machine-readable roadmap
                 \                    /
                  v                  v
                Bounded orchestrator <---- Persisted development state
                  |       |       |
                  v       v       v
               Builder  Validator Reviewer
                  \       |       /
                   v      v      v
                State + decision audit + prepared commit
```

The implementation deliberately avoids coupling development control to runtime business records. It reuses Intelligence Core principles—stable identifiers, fail-closed decisions, deterministic serialization, provenance, and bounded audit events—without creating a distributed workflow system.

## Authoritative artifacts

| Artifact | Purpose |
|---|---|
| `config/intelligence-core-development-state.json` | Current milestone, completed/blocked work, repository and test state, limitations, next increment, decisions and provenance |
| `config/intelligence-core-roadmap.json` | Ordered tasks, prerequisites, actions, risk, scope, acceptance, tests, stop conditions, dependencies and successors |
| `config/development-authority-policy.json` | Allowed development actions, owner-required actions and prohibited actions |
| `.codex/skills/edn-intelligence-core-builder/SKILL.md` | Fresh-session operating doctrine and reconstruction sequence |

Chat history is not authoritative. A fresh builder reads these artifacts, then the referenced architecture documents and observed Git state.

## Standing authority

The policy uses named actions rather than a single broad autonomy flag. Routine repository reads and writes, synthetic tests, static validation, internal refactoring and repair, documentation, state/audit updates, local planning, and commit preparation are allowed. Authority is evaluated for every action declared by a roadmap task.

New data access, domain/classification expansion, external permissions or authentication, production mutation, external communication, financial/legal actions, destructive or irreversible work, material architecture changes, security weakening, human-authority or product-vision changes, material infrastructure cost, protected-branch integration, and indeterminate actions require the owner. Explicitly prohibited autonomous actions remain prohibited rather than becoming approval requests.

Unknown action names fail closed. Capability availability never supplies authority.

## Structured escalation

An escalation records the blocked task, reason, exact request, approval and decline consequences, minimum authority, reversibility, recommendation, and response options (`GO`, `NO-GO`, `CONDITIONAL GO`). This gives the owner a decision record without exposing internal reasoning or routine implementation detail.

If one task is owner-blocked, the selector may choose another eligible allowed task. The owner interruption remains visible and is never silently treated as approved.

## State and roadmap models

Development state records product/version, branch and milestone, completed/active/blocked/deferred increments, limitations, test and repository status, last validated commit, next work, owner decisions, external blockers, architecture references, timestamp, and provenance. Writes use a temporary file followed by an atomic replacement.

Roadmap tasks use stable IDs and record objective, prerequisites, action/authority requirements, risk, expected components, acceptance criteria, tests, stop conditions, dependencies, status, and successors. Duplicate IDs, missing prerequisites, and missing successors are rejected. Selection requires completed prerequisites and an allowed authority decision.

## Bounded autonomous loop

The loop validates branch and expected working-tree state before selecting work. It then evaluates authority, calls the builder adapter, validates, reviews, and repairs routine findings. Limits apply to tasks, repair cycles, and elapsed time. Repeated identical validation failures, unexpected repository state, authority ambiguity, material architecture conflict, builder failure, or exhausted limits stop the run.

Successful tasks update state, append audit outcomes, and produce a recommended commit message. Commit creation, pushing, merging, and deployment remain separate policy actions.

## Builder, validator, and reviewer

`DevelopmentAgent` is a small protocol. `ManualLocalAgent` is the safe initial adapter and performs no external execution; a future documented Codex SDK adapter can implement the same boundary without changing policy or orchestration.

Validation is supplied through a separate protocol. Review is also separate conceptually and checks validation success plus architecture, authority, security, regression, acceptance, scope, tests, documentation, and state accuracy. Routine findings return to the builder. Findings marked owner-required generate an escalation.

## Audit and provenance

Audit sinks record timestamped task selection, authority decisions, implementation starts, validation results, review results, repairs, completion, blocks, and escalation generation. Records contain decisions, reason codes, evidence references, and outcomes only. They do not contain chain-of-thought, secrets, source content, or live evidence.

## Restart and dogfood proof

Synthetic tests reconstruct state, roadmap, and policy from disk in a fresh process-shaped path. They prove:

- a routine task proceeds under standing authority;
- a failed test is repaired and revalidated without owner involvement;
- a new external permission stops for owner approval;
- an unknown action fails closed;
- a material architecture finding escalates;
- a blocked task permits another eligible routine task;
- persisted state and the real repository configurations identify `IC-010` as the next eligible increment while `IC-009-LIVE` remains blocked.

No test contacts an external service or production data.

## Security and operational boundaries

- Repository validation rejects the wrong branch and unexpected dirty paths.
- Authority is checked before builder execution.
- Audit payloads exclude internal reasoning and protected content.
- The default agent adapter cannot authenticate or call a service.
- Run budgets prevent an uncontrolled loop.
- Existing uncommitted IC-007/008/009 changes are declared and preserved.
- Live Calendar validation remains an external blocker and is not attempted.

## Current next increment

`IC-010` is complete and validated. `IC-011` is the next eligible routine development increment: a durable authority-bound session reference store. `IC-009-LIVE` remains blocked on owner-accessible authentication and must not block routine local development.

## Limitations

- The initial builder adapter is manual/local; no Codex SDK executor is bundled.
- Acceptance-criterion interpretation is supplied by the validator/reviewer rather than a generic natural-language engine.
- JSON state assumes one orchestrator writer at a time.
- Commit creation and all external effects remain outside this increment.
- The expected-dirty-path list must be intentionally updated as pre-existing work changes.
