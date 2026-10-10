# Synthetic durable provisional reservations

This bounded prerequisite adds `SyntheticReservationStore` beside the existing
pure scheduler. It does not change PR #53's review head or deploy to the Android
demo. No Outlook calendar transport, customer confirmation or SharePoint write
exists in this implementation.

The caller supplies a canonical UUID, positive job revision and SHA-256 content
hash. The ledger records those values; it does not independently attest that the
job exists, is approved or remains unchanged. Wiring canonical job mutations to
reservation invalidation is a separate acceptance requirement before unattended
operation. Incomplete email drafts remain drafts and are not fabricated into
complete manual requests.

Planning and publication share one protected-store lock. Fresh complete synthetic
calendar availability is combined with all active local reservations, including
travel/preparation buffers. The existing scheduler preserves the Monday–Friday
10 am–3 pm Adelaide preference and customer-specified dates/times. Uncertain,
conflicting, uncovered or outside-default proposals remain proposals and cannot
become reservations through this API. Explicit night-work proposals therefore
still require the separate confirmation workflow.

The first reservation, optimistic rescheduling and cancellation retain actor,
UTC timestamp, job revision/hash, calendar scope/check time and original occupied
intervals. Cancellation releases the local interval without deleting its history.
Repeated identical job/request versions return the same durable receipt, without
claiming that calendar availability has been rechecked. A displayed old receipt
is not proof of current live availability. Stable reservation keys survive moves.
Malformed occupied data blocks new bookings rather than silently freeing time.

Storage reuses Work Intake's atomic private SQLite snapshots and anchored locking:
Linux/WSL only, private directories/files, sidecar rejection and containment.
Native Windows refuses before storage creation. The pilot is bounded to 1,000 jobs.
The caller creates a fresh synthetic-only private directory outside the repository
and explicitly initialises this separate ledger; existing operational stores are
not migrated or modified. Rollback is reverting this feature branch; do not delete
or downgrade a retained ledger as part of rollback.

Validation covers restart/replay, races with occupied buffers, audited reschedule
and cancellation, unchanged prior reservations after failed moves, corrupt data,
stale/incomplete availability, uncertain duration, read-only refusal and exact
version/hash conflicts. Full hosted Linux and Windows baseline checks plus exact-
head independent QA and Dot technical acceptance are required before integration.
