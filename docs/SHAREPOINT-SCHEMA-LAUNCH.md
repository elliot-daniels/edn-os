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

Storage is fixed to the approved `pilot-private/schema-8e4599f-one-shot` folder.
Read-only PowerShell 7 ACL verification runs before and after authentication.
Preparation uses CodexSandboxOffline
(`S-1-5-21-2158520141-276418557-3228345628-1003`). Network-enabled execution must
use exactly CodexSandboxOnline
(`S-1-5-21-2158520141-276418557-3228345628-1004`). The preparation SID remains
the expected folder owner; ownership carries ACL-management rights but does not
substitute for an execution identity or data-access ACE. The required protected
ACL permits only Admin, SYSTEM and Administrators Full Control, and Online
Modify/Synchronize. Offline has no required data-access entry. No inherited or
additional entries are accepted.

The launcher must be invoked after the host enables network access and switches
identity. It verifies actual identity and ACL before constructing MSAL and again
before constructing the Graph transport. An earlier offline check never suffices.
The launcher itself cannot switch Windows identity or edit ACLs.

Local correction status: Online SID was resolved and confirmed with whoami after
the transition. Set-Acl failed with missing SeSecurityPrivilege; subsequent Online
ACL inspection was denied. The required ACL and Online create/read/delete check
are NOT yet validated. An owner must apply the exact ACL above, preserving the
recorded owner, before further authentication. The earlier successful filesystem
test was under Offline and does not establish Online readiness.

The wrapper rejects reparse ancestors, Git ancestry, known cloud-sync paths and
nonempty output. The owner must prevent path/ACL replacement during execution.
Known OneDrive roots were checked; unregistered sync software cannot be ruled out.
No existing pilot retention deadline was changed.

The executor creates only minimized `schema-inspection.json`, exclusively, at
actual execution start. Its deletion deadline is that UTC start plus seven days.
No artifact, attempt marker or retention clock was started during preparation.
An existing artifact blocks replay, including a stopped attempt. Never delete it
to retry without separate owner approval. No automated deletion service exists.

Prior validation: 134 focused tests passed (17 launch cases plus 117 planner/executor
cases); Ruff and configured strict mypy passed (129 files). Real read-only wrapper
storage validation passed. Full suite was not rerun for this preparation stage.


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
