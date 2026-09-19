# Prepared schema launch — not executed

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
returned Graph scope set must equal Sites.Selected. The MSAL ID-token claims
must match tenant, application audience and account. A broader scope result
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
