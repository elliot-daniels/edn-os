# Synthetic synchronisation receipts

This is a private local fake transport, not a Microsoft client. It makes no network
requests and uses no tenant, credentials, scopes or real SharePoint item IDs.
Every receipt says `mode=synthetic` and `live_synced=false`, including `synced`.
The UI must label that state as synthetic and keep live SharePoint not synced.

An attempt binds the exact approved request revision, content hash, delivery key
and canonical payload digest. A pending receipt is persisted before transport.
Failed transport has no simulated item and permits an explicit retry. Unknown
means the acknowledgement was lost; a durable fake ledger may already contain
the simulated item. Pending/unknown blocks another delivery until reconciliation.
Reconciliation checks that exact ledger identity and either confirms the same
synthetic item or records a known failure if no item exists. Repeated successful
delivery returns the prior receipt without creating another synthetic item.
Changed payloads cannot silently reuse a delivery key.

Manual submission identity remains stable. Synthetic delivery identity derives
from that key, canonical work UUID, approved revision and approved content hash.
Each approved version has its own receipt, while the private receiver work record
keeps one synthetic identity across versions. Known failed/successful versions
allow a newly reviewed version; any pending/unknown version blocks delivery of
later versions until explicit reconciliation. Older unconfirmed receipts expose
only identity/status/audit metadata and can be reconciled without caching source
bodies in the UI. A bounded descriptor-relative scan refuses stores exceeding
3,000 entries. This is a synthetic demo bound, not an operational migration.

Receipts and ledger use existing Linux/WSL protected-storage contracts: private
owned directories/files, bounded reads, descriptor-relative operations, serialized
lock, complete staged writes and fsync before atomic publication. Native Windows
refuses before opening storage. A post-publication fsync failure is an uncertain
commit: reload/reconcile; never infer rollback or live success from an exception.
No destructive cleanup or real-store migration is performed.

Required validation includes failure/retry, lost acknowledgement/restart, explicit
reconciliation, content mismatch refusal, native unsupported-platform refusal and
full hosted Linux/Windows gates plus independent exact-head review.

## Send-time approval authority (F45-01 / WI-SP-08)

The sender must be constructed with its `IntakeStore`. A caller-provided approval
alone grants no delivery authority. `authorise_delivery` holds the protected intake
lock until synthetic publication finishes. It reconstructs the exact current
export, checks revision/state/content hash/submission key, fields, approval actor
and timestamp, target/provenance and attachment association, and verifies stored
evidence again. Edited, cancelled, unknown or evidence-mutated requests get a typed
refusal before any transport receipt or ledger write. The check itself writes no
database changes. All receipt/fault/restart tests now use actual approved records;
the fabricated envelope remains only for pure negative/identity tests.

## Existing website items (F45-02 / WI-SP-14)

`reference_existing` is reference-only. The synthetic sender refuses it with no
receipt, ledger or new work identity. The composed UI disables item delivery for
these records. No live read/write or new Microsoft permission is introduced.
