# PA-009 — Protected Preflight-to-Dispatch Handoff

Status: repository implementation and synthetic validation complete. No genuine
Microsoft retrieval or OpenAI dispatch occurred in this increment.

## Lifecycle

`OpenAIProvider.protected_preflight()` performs the existing disclosure checks
and provider preflight before writing anything. A denied projection is never
persisted and preflight never invokes provider transport. An allowed projection
is stored as a short-lived envelope. A later process reloads it through
`approve_protected()`, recomputes the exact canonical preflight hash, and binds
owner approval to that hash and the envelope expiry.

`generate_protected()` atomically renames the active file to a claimed file
before validation or transport. It then rechecks request, provider, exact model,
policy, domain, classification, categories, evidence count, expiry, projection,
prohibited content, approval and credential. Only one claimant can reach the
transport boundary. A successful or terminal attempt logically removes the
claimed file. This is invalidation and logical deletion, not a claim of secure
physical erasure from SSD or backup media.

One retryable network/provider failure may restore the envelope to active state
with a persisted attempt count. A second attempt is terminal. Successful use,
invalid response, missing credentials, authority mismatch, cancellation and
expiry make the envelope unusable. Existing daily request, success, retry and
spend controls remain in force.

## Protected storage

The default location is:

```text
$XDG_STATE_HOME/edn-intelligence-core/provider-preflights/
```

When `XDG_STATE_HOME` is unset it is:

```text
$HOME/.local/state/edn-intelligence-core/provider-preflights/
```

The dedicated directory must be owned by the effective process user with mode
`0700`. Each canonical JSON envelope must be a regular file owned by that user
with mode `0600`. Symbolic-link following is disabled where the platform
provides `O_NOFOLLOW`; unsafe type, owner, mode, canonical form, size, absence or
expiry fails closed. Exclusive creation prevents silent replacement, and an
active-to-claimed atomic rename prevents duplicate dispatch.

The envelope contains only lifecycle metadata and the exact sanitised
provider-visible projection: request ID, purpose, projection items, projection
size/redaction markers, model output limit, classification, domain, provider,
model, disclosure policy, categories, evidence count, preflight hash, creation,
expiry and retry attempt count. It does not persist source payloads, email or
document bodies, attachments, authentication tokens, API credentials, internal
principal identity, internal capability identity, unrestricted source
references, complete provider prompts or provider responses.

## Canonical binding

SHA-256 is computed over UTF-8 JSON with sorted keys, compact separators and no
ASCII rewriting. The binding includes the exact projected item values and order,
request/projection IDs, provider, pinned model, policy, domain, complete
classification metadata, categories, evidence count, projected character size,
purpose, output limit, redaction metadata, creation and expiry. Reload performs
the same serialization and preflight checks immediately before any credential or
transport use.

## Validation boundary

Synthetic fake-transport tests cover cross-process survival, exact reload,
value/request/model/policy/category/count tampering, expiry, unsafe directory and
file permissions, missing files, prohibited content, kill switch, successful
single use, replay denial, terminal failure deletion and the single retry path.
No automated test authenticates, reads live evidence or contacts OpenAI.
