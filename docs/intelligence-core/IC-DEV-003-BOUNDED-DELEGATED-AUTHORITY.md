# IC-DEV-003 — Bounded Delegated Authority and Autonomous Sessions

Status: repository implementation and synthetic validation complete. No grant
was created or activated by this increment.

## Purpose and authority boundary

A bounded delegation lets the owner approve a closed set of repetitive EDN OS
operations once for an absolute interval of at most seven days. Consumers claim
one unique operation ID, revalidate immediately before acting, and record only
metadata lifecycle events. The grant authorizes no operation by itself: existing
Git checkpoint, PA-005 source, PA-009 disclosure, credential, durable budget,
retry, protected-preflight, strict-schema, citation, result-retention and replay
controls remain independent mandatory enforcement points.

The design reduces natural-language approval frequency for routine repository
work and exact already-approved PA-005/PA-009 workflows. Scope drift, expiry,
revocation, kill switch, new authority, or consequential work still stops for an
owner decision.

## Grant binding

`DelegatedGrant` canonically binds:

- grant and owner identity;
- exact absolute repository root and `feature/*` branch;
- start and absolute expiry, with a maximum seven-day duration;
- closed operations and exact repository path prefixes;
- the three existing PA-005 scopes: default Calendar with category `EDN`, `/me`
  Inbox with category `EDN`, 25-item/one-page limit, and the exact approved Local
  Files root;
- provider `openai.api`, model `gpt-5-mini-2025-08-07`, policy
  `openai-daily-brief-pilot-v1`, the existing four metadata categories, EDN
  confidential classification/domain, and only the already-approved credential
  mechanisms;
- unchanged limits of two requests, one success and one retry per UTC day, AUD
  $2 daily/AUD $20 monthly spend and 2,000 output tokens; and
- an owner-named kill-switch identifier.

The owner approval repeats the exact grant ID, owner ID, integrity hash and
expiry. Changed, duplicate or replayed grants fail closed. The implementation
contains no API for extending an active grant, increasing limits, adding scope,
or disengaging its kill switch.

## Exact delegable operations

- repository read/write within exact grant paths;
- pytest, Ruff, mypy and static validation;
- stage, validated commit and push only to the exact existing feature-branch
  upstream after independent Git preconditions pass;
- bounded PA-005 Calendar, Inbox and protected Local Files reads using only the
  fixed existing scopes and their independent controls;
- PA-009 metadata-only budget check, credential-presence check, protected
  preflight, exact hash-bound dispatch, and read-only retained-result review.

PA-009 dispatch requires an exact preflight hash plus confirmation that all
underlying controls were independently revalidated. The delegation cannot admit
or reserve budget, manufacture provider approval, alter the ledger, weaken
retry/replay controls, or make invalid output retainable.

## Permanent exclusions

New credentials/scopes, Microsoft permissions, data sources/folders/roots,
disclosure categories, security weakening, budget increases, main/protected
branch work, merge/rebase/force push, destructive external actions,
notifications/delivery, purchases/financial actions, production deployment,
long-lived secrets and PA-010 are never delegable. Unknown operations are also
denied.

## Protected storage and lifecycle

The default store is
`$XDG_STATE_HOME/edn-intelligence-core/delegated-authority/` with the existing
`$HOME/.local/state` fallback. It requires effective-user ownership, directory
mode `0700`, SQLite mode `0600`, a safe regular non-symlink path, restrictive
creation umask, full SQLite synchronization and `BEGIN IMMEDIATE` transactions.

The canonical grant is SHA-256 bound. Operation IDs are unique durable claims;
a concurrent duplicate or a crash after claim cannot replay the operation. A
consumer calls `validate_claim()` immediately before action. Expiry, owner
revocation or the one-way kill switch invalidates both new and already-issued
claims. Claims can transition once from claimed to completed while the grant is
still active.

The audit records only grant ID, closed event/reason codes and timestamps. It is
sequence- and hash-chained. It stores no paths, source/evidence values, prompts,
credentials, approval secrets, provider responses or operation payloads.

## Operational adoption

The repository now supplies the protected grant and claim boundary. A first
owner grant can authorize a local Codex/session adapter to claim and revalidate
routine operations instead of asking for another natural-language `GO` at each
internal checkpoint. The host/sandbox may still require platform-level command
approval; a repository grant cannot and must not bypass that control.

No generic executor is added. PA-005/PA-009 callers must be explicitly wired to
consume a claim at their existing enforcement point before any future delegated
live use. Until that wiring is invoked under an active owner grant, current
per-request workflows remain unchanged.

### Fresh-session adoption

`resolve_active(owner_id, repository_root, branch, now)` now reconstructs exactly
one active grant without requiring chat history or a copied grant ID. It reloads
and verifies every stored grant, then matches exact owner, repository and branch
inside the grant window. No match, expiry, tampering or multiple simultaneous
matches fail closed. The method returns authority metadata only and neither
claims nor executes an operation.

### Stable lifecycle command boundary

`python -m edn.development.delegation_cli` is the single narrow command prefix
for routine host approval of delegation-store access. It provides only:

- `resolve`, which identifies the one exact integrity-validated active grant;
- `claim`, which durably claims one declared operation after the existing grant
  checks admit its exact paths, source scopes, Git preconditions or PA-009
  bindings;
- `validate`, which revalidates one claimed operation immediately before work;
- `complete`, which terminally completes one exact claim; and
- `claim-status`, which reads the bounded lifecycle metadata needed for crash or
  interruption reconciliation.

The command does not activate, broaden, extend, revoke or kill a grant. It also
does not run Git, tests, source retrieval, credential access, provider transport
or any claimed operation. PA-005 claims still require an exact approved source
scope and an explicit assertion that their independent controls passed. PA-009
claims still require the grant-bound credential mechanism and independent
control assertion; dispatch additionally requires the exact protected-preflight
hash. Git claims still require explicit validation and exact-upstream
preconditions.

Output is canonical metadata-only JSON containing grant or claim identity,
operation and closed lifecycle outcome. It never returns source scopes,
categories, paths, provider payloads, credentials or operation inputs. Operation
IDs use a bounded safe character set. The CLI verifies the grant binding and
hash-chained audit before every command, and expiry, revocation, kill switch,
tampering, ambiguity, scope drift and replay continue to fail closed.

Every newly created claim row is also canonically SHA-256 bound across operation
ID, grant ID, operation, state, claim time and completion time. Both validation
and completion verify that binding, and completion atomically replaces it with
the terminal-state binding. The additive migration does not bless legacy rows:
pre-migration claims remain unbound and therefore cannot become executable under
the new CLI. At migration time all 25 legacy claims were already completed and
there were no active or orphaned claims. Dispatch claim input additionally
requires the preflight hash to be exactly 64 lowercase hexadecimal characters;
the protected-preflight boundary still independently verifies its meaning and
byte identity.

## Residual PA-009 validation

The owner provisionally accepts PA-009 for continued development. Repository and
synthetic temporal validation passed, but one genuine retained-result lifecycle
must still prove historical evidence is correctly labelled and cannot produce a
time-invalid action when the unchanged daily PA-009 budget next permits it. This
is technical debt, not a completed proof and not permission to reset or reinterpret
the ledger.
