# Opaque provider resource identity repair

Local-only repair from `f17c63599e7d02fb9260cabe6c2da13d4dc07e37` on
`feature/executive-brief-reliability`. No live pilot was resumed.

## Cause and offline reproduction

The stopped pilot resolved a 152-character native Graph Calendar ID containing
padding. Calendar adapters passed that text directly into policy resource scopes.
Core correctly rejected it: durable identifiers are 1–128 characters from
`[A-Za-z0-9._:-]`, with additional delimiter restrictions. Calendar provenance
would independently have failed when the same value reached SourceRef.
Inbox aliases avoided the immediate policy error but default folder scopes and
opaque mailbox provenance had the same latent boundary problem.

The protected local report and audit were read before editing. Both original
failures were reproduced offline using the actual resolved Calendar ID; neither
the ID nor the artifacts are committed. The initial new mapping test failed
collection because the abstraction did not exist. After repair, both actual
resolved Calendar/Inbox IDs passed local policy/provenance construction and
exact serialization checks. Synthetic fixtures contain invented IDs only.

## Architecture and compatibility

`connectors/resource_identity.py` introduces immutable ProviderResourceIdentity:
provider, tenant, account, resource kind and exact provider ID. Its internal ID
is `provider-v1:` plus the full SHA-256 of an unambiguous JSON tuple. No native
text is trimmed, decoded, case-folded or truncated. This is collision-resistant,
not a mathematical promise that a finite hash can never collide. Tenant,
account, resource kind and mailbox parent distinguish otherwise identical IDs.
Mapping survives process restart without a database or new service.

Calendar and Outlook configs derive mappings at construction, failing closed
on missing/blank/control-character input. Adapters, CLI/request builders and
connector checks use mapped authority. Retrieval continues using exact native
Calendar, mailbox and folder IDs. A changed native target receives different
authority; possession of provider text or a mapping does not grant access.
Legacy Outlook folder aliases remain validated configuration labels and no
longer supply independent authority. Old raw-ID/alias policies must be rebuilt
for their exact configured mapping; there is no permissive fallback.

SourceRef adds optional `provider_resource_id` for exact opaque provenance.
Existing durable source fields still use the unchanged validator. Old references
serialize exactly as before when the optional field is absent. Calendar source
references identify the mapped calendar; mail references identify the mapped
folder (whose namespace includes its mailbox). Native record keys remain exact.
Locators stay bounded even for very long resource IDs. Connector provenance
rejects events/messages from unmapped resources. Evidence IDs incorporate the
internal source namespace, avoiding cross-account citation ambiguity.

The mapping intentionally changes affected source/evidence identities. Historical
references remain readable; no stored references or policy grants are rewritten.
Hosts must record/review the native-to-internal binding in a new run's audit.

`src/edn/core/security.py` and the policy evaluator are unchanged. The validator
SHA-256 is `502474737f99d49e67cb67e49838858228336b328cedf9c68dfa71d1040fd8e4`.
No POSIX protected-store checks were weakened.

## Validation

- 37 new tests pass: long/padded/punctuated/Unicode IDs, distinct namespaces,
  exact serialization, independent-process stability, invalid mappings, policy
  rejection and a synthetic run through MorningBriefApplication with network
  blocked. Both legacy evidence adapters and morning source adapters agree.
- Full suite: 659 tests; 566 passed, 92 failed, one skipped. All 92 failure
  identities exactly match the recorded Windows baseline: zero additions and
  zero missing baseline failures. Relevant Core/Connector/Intelligence tests
  also introduced no failures outside that baseline.
- Ruff, strict mypy using the existing Linux platform target (124 source files),
  and git diff whitespace validation pass.
- Exact failure IDs and validation evidence hashes are in
  `opaque-resource-identity-validation.json`.

Changed implementation: the shared mapping module, Calendar/Outlook models and
connectors, Calendar CLI, legacy/morning intelligence adapters, PA-005 request
builder and SourceRef. Tests update scope construction and add dedicated mapping
and end-to-end regression coverage. No HTTP client or projection was broadened.

## Owner boundary

The original one-shot approval can be reissued with the same data-access scope:
same tenant/application/account, category admission, field projections, windows,
caps, retention and prohibition on writes/providers/schedules. No new Microsoft
permissions or consent are needed for this local representation repair.
Fresh explicit approval and identity/storage verification remain required before
another run. The host must use this repaired code and record both mapped and
native identities; do not reuse old raw-ID grants or a consumed run marker.
The original retained artifacts still expire by 2026-09-23 09:15:46 UTC; any
new run's retention must not extend that deadline for the original artifacts.

During this repair: zero Microsoft authentication/GET/write calls; zero provider
calls; no SharePoint or UWC access; no recurring schedule, deployment, merge or
PR. Pilot artifacts stayed outside Git with their ACLs and deletion deadline
unchanged. Only the authorized feature branch is published.
