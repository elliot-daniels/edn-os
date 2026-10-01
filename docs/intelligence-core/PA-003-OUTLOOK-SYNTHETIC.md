# PA-003 - Synthetic Current Outlook Read

PA-003 adds a read-only Microsoft Outlook connector contract and source-neutral
Intelligence adapter. It operates only over an injected client; no HTTP,
authentication or token implementation exists in this increment.

Configuration binds tenant, account, mailbox, exact folder IDs, domain,
classification and either a dedicated EDN mailbox or exact category filter.
Capabilities are limited to `outlook.search` and `outlook.verify`, both
requiring `Mail.Read`. Retrieval windows and result counts are bounded.

The admitted projection contains subject, sender/recipient routing metadata,
received/modified timestamps, importance, read status, categories and web
provenance. Any Graph-shaped payload containing `body`, `bodyPreview` or
`attachments` fails closed. No send, move, delete, mark-read or other mutation
operation exists.

All automated validation uses an in-memory synthetic client. Live Graph access
and Microsoft authentication remain owner-blocked under PA-005.
