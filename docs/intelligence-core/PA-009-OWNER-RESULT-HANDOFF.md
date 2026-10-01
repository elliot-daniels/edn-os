# PA-009 — Protected Owner-Review Result Handoff

Status: repository implementation and one genuine post-process retained-result
proof passed. That review exposed a separate temporal-projection defect, now
addressed by `PA-009-EVIDENCE-FRESHNESS-AND-TEMPORAL-VALIDITY.md`; the handoff
schema and authority boundary are unchanged.

## Boundary

`OwnerReviewResultStore` persists a result only after the OpenAI response has
passed provider/request/model/policy echo checks, the strict closed Structured
Outputs schema, statement semantics and disclosed-evidence citation membership.
Invalid, incomplete, refused, schema-invalid, citation-invalid and transport-
failed results never enter the store. A result-store failure is terminal,
non-retryable, preserves deterministic fallback and cannot strand or restore a
protected preflight claim.

The default owner-local path is:

```text
$XDG_STATE_HOME/edn-intelligence-core/provider-results/
```

When `XDG_STATE_HOME` is unset it is:

```text
$HOME/.local/state/edn-intelligence-core/provider-results/
```

The directory is effective-user owned mode `0700`. Canonical result files are
effective-user owned regular non-symlink files mode `0600`, opened with
`O_NOFOLLOW` where supported. A file is written and fsynced under a random
owner-only temporary name, atomically published without replacement, validated,
and followed by directory fsync. Duplicate request IDs fail closed.

## Retained closed schema

The store retains exactly:

- request ID and exact protected preflight hash;
- provider, pinned model and disclosure policy;
- security domain and complete classification metadata;
- creation and expiry timestamps;
- fixed `passed` schema- and citation-validation outcomes;
- ordered validated statements containing only kind, bounded statement text,
  validated disclosed evidence IDs, bounded uncertainty and `proposal_only`.

The result is model output for owner review, not verified fact. Statement text is
limited to 2,000 characters, uncertainty to 1,000 characters, statements to ten
and evidence references to 25 per statement. Unsafe control characters and
invalid identifiers fail closed. Proposed actions must remain
`proposal_only=true`; no other statement kind may acquire proposal authority.

The canonical document contains a SHA-256 integrity binding over the request,
preflight, provider, model, policy, domain, classification, timestamps,
validation outcomes and every retained statement field in order. Any mutation,
truncation, additional field, type coercion or non-canonical serialization fails
readback.

Prompts, raw or partial Responses payloads, refusal text, projection values,
source content or records, email/document bodies, credentials, authorization
headers, approval tokens, protected-preflight contents and arbitrary provider
metadata are prohibited. Durable lifecycle audit remains metadata-only and
separate from this owner-review result.

## Owner review and retention

`load(request_id)` is an exact, read-only review boundary. It validates the
directory and file type, ownership, mode, canonical bytes, integrity hash,
closed schema, statement semantics and expiry before returning grouped typed
statements. It has no preflight, approval, retry, dispatch, provider, connector
or external-action method and cannot reconstruct provider authority.

Default retention is 30 days and cannot be configured longer. Expired results
fail closed and are removed without changing lifecycle audit, budget state or
provider authority. `remove_expired()` removes only safely decoded expired
results; corrupt files remain fail closed for explicit investigation.

## Protected-preflight hygiene

`ProtectedPreflightStore.reconcile()` reads only the minimum envelope lifecycle
metadata returned to its caller: request ID, creation, expiry, active/claimed
state, disposition and removal status. Projection fields are never returned.
It classifies envelopes as:

- `active_valid` — left untouched;
- `expired_removed` — invalidated through the safe existing removal path;
- `claimed_in_flight` — left claimed so unknown transport cannot replay;
- `terminal_orphan_removed` — removed only with durable terminal evidence; or
- `corrupt_unknown` — left fail closed and never made dispatchable.

Reconciliation creates no approval, result, projection or transport path. The
first authorised hygiene run found two unrelated active envelopes, proved both
expired from their protected lifecycle metadata, removed both, and found zero
claimed envelopes.

## Remaining temporal proof gate

Routine PA-009 use remains blocked until one fresh, separately owner-approved
protected lifecycle demonstrates genuine historical evidence is labelled and
cannot generate a time-invalid action. Delegated or autonomous authority remains
out of scope.
