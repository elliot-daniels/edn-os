# Exact filter values and reset identity

Issue #33. The read-only Operations Inbox uses `None` exclusively for reset. Stored strings, including `All` and `Value: All`, retain exact query identity. Every stored value has a consistent display prefix so reset and real values cannot have ambiguous labels.

Regression coverage selects literal values and resets each source/client/project/job control, checks exact rendered rows and verifies database bytes are unchanged. The existing reset test selects the typed reset value with its original assertions retained. No timeout, schema, migration, source write or security gate changes. This is a prerequisite for persistent triage; OCT-05 remains open.
