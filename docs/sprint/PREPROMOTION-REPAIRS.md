# October pre-promotion repair candidate

Base: 48d902ef9e98c17c0488bc7164d3d9bf9c0a01a9. Branch:
feature/october-prepromotion-repairs. Exact delivery SHA is supplied in the
external repair report and source bundle; the checkout HEAD identifies it.
Status: HOLD for baseline promotion; no main authority has been changed.

## Four findings repaired

1. Schema authentication: before, fixed identity plus Sites.Selected allowed
   additional User.Read/Mail.Read/Calendars.Read Graph scopes. Now only exactly
   Sites.Selected survives existing Graph-prefix normalization/OIDC handling.
   Broader tokens are rejected before transport/executor construction. Retain
   identity checks, single-scope requests, redacted diagnostics, unique run storage,
   schema typing and fixed three/seven-request guards. No repository evidence
   demonstrates a necessary approved broader schema use case; the historical
   owner-reviewed wording alone does not establish one. A shared-app token with
   extra Graph grants may fail this narrow path; that is intentional. Any proven
   future compatibility requirement must go to Elliot before broadening. Separate
   Operations mail authentication retains its own approved-scope model.
2. Redirects: default Outlook transport rejects all redirects before another
   request. Authorization is an unredirected header, so even an injected standard
   urllib redirect handler cannot copy it cross-origin. In-memory HTTPS fixtures
   test 301/302/303/307/308 across host, scheme and port changes; no sockets used.
3. Bounds: actual read(MAX_RESPONSE_BYTES + 1), cap 1,048,576 bytes independently
   of record count; reject more than 50 records before persisting that page,
   independently of response size. Existing 31-day/100-page bounds retained.
   Regression fixtures cover exact/overflow bytes with zero records, oversized
   single-record responses, and small 50/51-record pages. Earlier completed pages
   remain durable/replay-safe after a later page fails.
4. Attachment metadata: reject malformed containers, null/scalar/empty entries,
   wrong field types, negative/bool/string sizes, binary/unknown fields before
   Event creation/storage. Revalidate nested metadata at serialization because
   frozen Events contain mutable dictionaries. Decoding validates before the
   read-only Inbox renders it; corrupt stored metadata produces a safe error
   without changing the DB. Existing source/provenance/replay architecture retained.

## Documentation and CI

Authority reconciliation distinguishes expired August grants and historical
Work Log state from current authority/connectivity. Frozen receipts, manifests,
audit chains and maker source are unchanged. The six Operations commits remain
ancestors; separate 4f76f91 solution/flow assets and 839e75c changes are excluded.
Source-of-truth docs now describe the narrow auth policy and implemented bounds.

PR workflow adapts 2d88a99/3faa51c manually, without merging UWC history. It uses
read-only permissions, no persisted checkout credentials or live secrets, no
deployment/push trigger, Linux Python 3.11/3.12 full pytest/lint/native strict types,
frozen integrity and whitespace/clean-tree checks. Windows full Python validation
uses exact failure identities/signatures, known skip and collection floor; it
never waives Linux protection failures. Dependencies remain ranges; runs record
resolved versions. Hosted workflow parsing/execution and protection are unverified.

## Validation and remaining gates

Windows/Python 3.12.14: complete Python suite expected collection is 1,068
tests; exact committed-head outcomes are in the external delivery evidence.
Focused repaired boundaries/auth/Inbox/state tests: 106 passed. Ruff and
Linux-targeted strict mypy pass (135 source files); JSON/JSONL/frozen hashes pass.
IMS Pester 3.4.0: 35 passed, 3 failed because Add-PnPField is unavailable for
mock construction. Untouched 48d902e gives exactly the same three identities
and reasons. No PnP command or live installer entry point was invoked.
The initial NUnit XML export also encountered an environment CIM access denial;
JSON result evidence was captured without that optional exporter. Windows is
not a supported protected-store environment; no security controls were bypassed.
The 92 Python baseline failures are 90 missing POSIX geteuid, one unavailable
symlink privilege, and one Windows root-path assertion mismatch. New or changed
failures, skips, errors or missing cases block PRs. Linux must pass all protected
store tests. Native Windows type errors on POSIX APIs are distinct from the
passing Linux-targeted type check.

Promotion blockers: exact-candidate Linux runtime suites on Python 3.11 and 3.12;
actual hosted PR workflow success and independent review on that SHA. No Linux
runtime is available here (WSL not installed; Docker/Podman absent), so Windows
Linux-targeted types cannot establish runtime safety. Owner-controlled required
checks and promotion authority must be in place before accepting the shared
baseline. Live storage/mail/staging acceptance remains separately gated and is
not authorized by this repair. IMS offline mocking requirements are documented
separately; no PnP installation, connection, consent or tenant mutation occurred.

Rollback: discard this isolated candidate, or revert its repair commit in a future
approved integration. The base and original Operations checkout are untouched.
