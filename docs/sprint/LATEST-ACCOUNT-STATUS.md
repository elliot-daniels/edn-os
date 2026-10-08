# Latest bounded import result per account

The Inbox now selects the newest recorded attempt for each account before applying
its 20-account display bound. Repeated attempts by one account cannot hide another
account's latest partial/failed result merely by filling the recent-attempt window.
Timestamp and run-ID tie ordering remains deterministic. Existing CLI/attempt
history and its bounds remain unchanged.

The view still describes requested Inbox windows only. More than 20 accounts may
have history outside this explicitly bounded view; it never infers completeness
from Events. Source bodies, exceptions and continuation URLs remain absent from
outcome metadata. Reads retain schema validation and never initialize a store.
This does not solve active/stale importer ownership or historical counter assurance,
and does not close OCT-06. Rollback: revert query/display; no schema/data migration.
