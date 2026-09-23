# Prepared schema launch - separately approved execution only

The dedicated `schema_launch` module wraps `SchemaExecutor` and
`SchemaHttpTransport`. Importing it performs no I/O. The explicit CLI flag
`--approved-authenticate-and-inspect` is required, but does not itself confer
owner authority. Do not invoke it until authentication and one inspection are
separately approved. No authentication occurred during preparation.

The future invocation from the repository root is:

```powershell
$env:PYTHONPATH = 'src'
& 'C:\Users\Admin\Documents\Codex\2026-08-28\referenced-chatgpt-conversation-this-is-an\work\edn-os\.venv\Scripts\python.exe' -m edn.connectors.microsoft_sharepoint.schema_launch --approved-authenticate-and-inspect
```

MSAL uses the fixed EDN tenant/application and Elliot's account, auth-code/PKCE,
loopback port 8400 and an in-memory token cache. Only
`https://graph.microsoft.com/Sites.Selected` is requested as a Graph scope.
OIDC sign-in scopes are protocol metadata; offline_access is excluded. The
returned Graph scope set must contain Sites.Selected and be a subset of the
explicit shared-application allowlist: Sites.Selected, User.Read, Mail.Read,
Calendars.Read. The MSAL ID-token claims
must match tenant, application audience and account. Any scope outside that allowlist
fails closed; never silently trim its scope metadata. The owner completes sign-in
personally and must stop at any unexpected consent screen. No token or raw
authentication result is printed or serialized. No refresh/retry supplier is used.

The exact owner-supplied read permission ID is fixed in the wrapper. No permission
enumeration, administrator session or operational connector is used. The existing
planner and both execution guards retain all seven-GET restrictions.

## Protected parent and unique run storage

The fixed owner-approved parent is:
`C:\Users\Admin\Documents\Codex\2026-09-14\files-pasted-by-the-user-edn\pilot-private\schema-8e4599f-one-shot`.
It is not a configurable arbitrary output root. Each separately authorized CLI
invocation creates exactly one `run-<UUID4 hex>` child with exclusive mkdir.
For example, a synthetic child is `schema-8e4599f-one-shot/run-00000000000000000000000000000001`.
Randomness avoids collisions; it is not an access-control mechanism. Existing
empty/nonempty children are never reused, removed, or selected automatically.
Authentication failure can leave an empty child; it is not an inspection artifact.

The parent is checked before child creation. Both paths and all ancestors reject
reparse points, symlinks, Git ancestry and known cloud-sync roots. Child names
must match the exact lowercase UUID naming grammar. Both lexical direct-parent
and strict resolved direct-parent equality are required. Alternate roots,
traversal, absolute injection and ambiguous resolution fail closed. The parent
may contain older runs; `storage_not_empty_or_prior_attempt` still applies to the
selected child, in both launcher and executor. No old retention deadline changes.

Network-enabled execution still requires CodexSandboxOnline SID
`S-1-5-21-2158520141-276418557-3228345628-1004`.
The protected parent retains exactly four explicit Allow ACEs: Admin, SYSTEM and
Administrators Full Control, Online Modify/Synchronize; owner is preparation SID
`S-1-5-21-2158520141-276418557-3228345628-1003`.
A newly created child must be owned by Online and inherit precisely those four
ACEs, with inheritance enabled, no explicit or unexpected ACEs. No ACL commands
modify permissions. ACL inspection is read-only PowerShell 7. If unavailable,
stop for the established owner/admin verification process; historic parent-only
attestation cannot verify a new child's ACL, and no generic trust bypass exists.

Before authentication, the child passes ACL/containment checks and an exclusive
harmless create/write/read/delete test. The file is removed in a finally block;
failed deletion or verification stops execution. Revalidation occurs after the
probe and again after authentication immediately before transport construction.
The owner must prevent concurrent path/ACL replacement. Known sync-root checks
cannot discover unregistered sync software.

Only when SchemaExecutor begins retained inspection output does the exclusive
schema-inspection.json manifest start its UTC retention clock. It records run_id,
artifact_created_at, started_at, and delete_by exactly seven days later, including
stopped attempts. Synthetic test directories do not start any live retention.
Every save includes manifest_content_sha256: SHA-256 of canonical sorted compact
JSON excluding that hash field itself. Completed runs also retain schema_sha256.
This is a content hash, not a self-referential whole-file hash; a whole-file SHA-256
can be calculated read-only for the owner report. No tokens/raw responses are
persisted and no automated deletion service is installed.

## Deterministic delivery correction (local/synthetic only)

Authentication prints flushed, sanitized milestones: AUTH: preparing; authority
ready; browser handoff starting; browser handoff accepted or failed; waiting for
browser completion; callback received; validating identity and scopes; success,
or a static failure/cancellation stage. Callback received is reported when MSAL
returns from the interactive call (including its token exchange), not a separate
instrumentation hook into the HTTP callback handler.

MSAL construction now sets a 20-second HTTP timeout. This bounds connect/read
waits for discovery and token exchange; it is not an overall 20-second authority
transaction deadline. MSAL 1.38.0's own HTTP adapter can retry once, and discovery
may involve multiple requests. The separate browser/callback wait remains 600
seconds. No Graph retry policy was changed. Discovery errors, callback timeout,
identity/scope failures and cancellation block all Graph execution. A failed OS
handoff is recorded and blocks execution even if a result subsequently arrives;
MSAL may remain waiting until its finite interactive timeout.

A process-scoped webbrowser.open hook observes the existing system-browser
handoff and is restored on exit. It accepts only the fixed local landing URL.
It does not launch a device-code, broker or embedded-browser flow. MSAL receives
its supported welcome_template and static success/error templates. Elliot sees
an EDN localhost page with a Continue to Microsoft sign-in link, then the normal
account/MFA interaction. Never accept unexpected consent. The localhost return
page says authentication returned and directs Elliot back to Codex for results.

An accepted handoff is not proof of a visible window. The printed fallback is
only http://localhost:8400?welcome=true, which Elliot can open while this same
attempt is active. The Microsoft authorization URL is rendered only in the
memory-only loopback page, never printed or saved by the launcher. Library logging
is suppressed during authentication and restored afterward so MSAL exception or
URI diagnostics cannot leak sensitive material. Do not enable debug logging or
export browser contents during authentication. No token cache is serialized.

No new Entra setting is implemented or verified. Existing localhost desktop
redirect compatibility and browser accessibility still require the next separately
approved live attempt. This CLI is single-launch/process scoped and not intended
for concurrent use inside a shared application process. All storage, scope,
identity, retention and seven-request execution guards remain in effect.

## Safe validation diagnostics

Validation failures now print an allowlisted `reason=authentication_*` code:
result_invalid, response_error, consent_required, claims_missing, tenant_mismatch,
client_id_mismatch, account_mismatch, required_scope_missing, unexpected_scope,
scope_format or token_invalid. Checks stop at the first failure. No observed
claims, raw scope strings, provider descriptions or credentials are printed.
Only an explicit protocol `consent_required` error gets that classification;
missing claims/scopes do not prove that application consent is absent.

Sites.Selected must be present. User.Read, Mail.Read and Calendars.Read are
allowed token scopes for the verified shared EDN application only. They do not
confer operation authority on this schema executor. Account selection still requires Elliot, never the admin.
The result dictionary is cleared on validation success and failure. This is not
a claim of secure memory erasure. No authentication artifacts are persisted.

The prior generic identity-and-scopes failure cannot be diagnosed retroactively:
the result was not retained. Callback completion alone does not prove successful
token acquisition, because MSAL can return an error dictionary. A separately
approved attempt is required to obtain a new non-secret reason; no consent,
permission or account-policy change is implied by these diagnostics.

Unexpected-scope diagnostics report sorted exact recognized scope names only.
The safe vocabulary is Sites.Selected, User.Read, Mail.Read, Calendars.Read,
Sites.Read.All and Sites.FullControl.All. Unknown/case-variant values are
redacted and flagged. This display vocabulary never changes scope acceptance.

## Owner-reviewed shared application scope policy

The authentication allowlist applies only after the fixed tenant/application and
Elliot identity checks pass. Required: Sites.Selected. Allowed additional token
scopes: User.Read, Mail.Read, Calendars.Read. Unknown, malformed and case-variant
scope names fail closed. Exact https://graph.microsoft.com/ prefixes are removed;
OIDC metadata scopes retain the existing handling. Sets deduplicate and diagnostic
names are sorted. Requested Graph scope remains Sites.Selected alone.

SchemaIdentity.scopes describes the operation authority, not all token grants.
It remains exactly Sites.Selected. The executor and transport retain independent
exact-request, sequence and seven-request guards. Neither consumes allowed mail
or calendar scopes as capabilities. The minimized artifact's scope field records
operation authority, not the entire token scope set. No operational connector is
involved. This policy does not approve live authentication or schema execution.

Local shared-scope validation: 185 focused tests passed; full suite 800 passed,
92 failed, 1 skipped. Failure identities exactly match executive-baseline.xml
and guid-full-final.xml (zero new/resolved). Ruff, strict Linux-target mypy
(129 files) and diff whitespace checks passed. No Microsoft access in this change.

Unique-run storage changes are local/synthetic only. A future live invocation
must still pass actual Online parent/child ACL and filesystem guards. No live
authentication or inspection is authorized by these code changes.

Unique-run validation: 205 focused tests passed. Full suite: 820 passed, 92 failed,
1 skipped; failure identities exactly match executive-baseline.xml and
shared-scope-full.xml. Ruff, strict Linux-target mypy (129 files) and whitespace
checks passed. Real local-only storage validation under the exact Online SID
also passed parent/child ACL, containment and create/read/delete checks. Its
empty reserved child is run-377affc95716468bb36fa7100c78babf; no authentication,
retained schema artifact or retention clock was started. A future authorized
inspection creates a different child and repeats every guard.
