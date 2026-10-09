# Durable manual submission intent and receipt

Manual create requires a caller-stable canonical UUID submission_id. The UI first
calls begin_submission to durably reserve an explicit new intent; current_submission
returns that same intent plus its original normalized fields and any request receipt
after restart/lost response. Intent does not rotate on successful create or replay.
The operator explicitly starts the next request. A receipt and first draft revision
commit atomically in one protected SQLite snapshot. Same key/same initial facts
returns the current locally reviewed request; changed initial facts conflict without
mutation. Different keys with identical fields remain distinct requests. Later local
corrections/evidence do not rewrite the original receipt or create extra replay
revisions. Concurrent callers serialize through the protected store lock.

Explicit initialization adds version2 receipt/intent tables to a compatible core
version1 store; original requests, source revisions and audits remain unchanged.
Existing version1 manual requests receive deterministic local UUID receipt keys
from their request UUID and first revision. Malformed originals reject the entire
upgrade. No real runtime migration is performed. Old code rejects version2 rather
than weakening the receipt gate. Rollback disables the dependent UI and preserves
its local database; no destructive downgrade is automatic.

Export retains exact approved revision/hash/actor/time and full attachment manifest
outside the SharePoint fields, and includes submission_id/idempotency_key plus
truthful manual provenance. It remains a dry run and never claims Synced or sends
HTTP. Full hosted Linux tests and exact-head independent review remain required.
