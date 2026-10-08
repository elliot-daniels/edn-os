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

Receipts and ledger use existing Linux/WSL protected-storage contracts: private
owned directories/files, bounded reads, descriptor-relative operations, serialized
lock, complete staged writes and fsync before atomic publication. Native Windows
refuses before opening storage. A post-publication fsync failure is an uncertain
commit: reload/reconcile; never infer rollback or live success from an exception.
No destructive cleanup or real-store migration is performed.

Required validation includes failure/retry, lost acknowledgement/restart, explicit
reconciliation, content mismatch refusal, native unsupported-platform refusal and
full hosted Linux/Windows gates plus independent exact-head review.
