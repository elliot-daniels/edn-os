# Email intake pilot — preparation only

Owner's 10 October direction provides two real positive examples and ordinary
correspondence as negatives. It authorises synthetic development, not live reads
or cloud disclosure. No real message body, headers, attachment or derived content
belongs in this public repository, PR evidence or CI fixtures.

## Permissions and processing decision required before a live pilot

For an owner-mailbox delegated Graph reader, body/attachment reads require
`Mail.Read`; `Mail.ReadBasic` excludes bodies and attachments. A shared mailbox
may require `Mail.Read.Shared` and a separately verified access relationship.
Do not assume the connected account owns the intended business mailbox. The
existing Operations delegated identity check also uses `User.Read`. Inspect the
effective installed connector grants without retrieving mail or tokens before
claiming they meet this proposal. Availability of a tool does not establish its
OAuth grants. No consent expansion is authorised.

For complete bounded busy coverage of the owner's selected calendar, Graph
`calendarView` supports delegated `Calendars.ReadBasic`. Select only identity,
start/end and busy-state metadata needed for conflicts; avoid event bodies and
attendees. Shared calendars need independently verified permissions. Calendar
reads and any later writes have separate owner authority. No `Mail.Send`,
`Mail.ReadWrite` or `Calendars.ReadWrite` is needed for this read/propose pilot.

Sources: [Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference),
[calendarView](https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview?view=graph-rest-1.0),
[message attachments](https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0).
Checked 10 October 2026; these document minimum API permissions, not actual grants.

Preferred processing is the existing local Linux/WSL application in a separately
owner-approved encrypted real-data root with protected private storage. The
DigitalOcean Android demo remains synthetic-only. Moving real source data to
that host requires its own explicit data-location approval.

Reading message bodies through an Outlook connector in this hosted Codex chat
would return them into hosted OpenAI processing. That is a disclosure boundary,
even if no separate model API is called. Forwarding alone does not authorise it.
Local extraction without an external provider is the default. Any OpenAI/xAI
processing needs explicit provider, model, exact fields, permitted classification,
retention/data-handling terms and approval of the existing governed model boundary.
Do not transmit Memory email content to cloud AI.

The eventual owner approval must identify the exact mailbox/account, two message
IDs or tightly bounded read window, negative-example bounds, calendar and five-day
coverage, processing location, storage and disclosure choice. Do not request
credentials in chat. No mail read, calendar read/write or provider dispatch has
been performed by this preparation.

## Current implementation and acceptance limits

The local assessment prerequisite recognises seven distinct intents, extracts
explicit labelled facts with exact source quotes, preserves night/time text and
groups missing questions. It never creates bookings. Competing intents, including
quoted thread history, remain uncertain rather than granting scheduling authority.
Reported email facts are not verified CRM records. Unstructured extraction,
trusted relationship lookup, durable incomplete drafts, answer continuation,
cross-forward/thread duplicate reconciliation, reservation transactions and mobile
presentation remain separate implementation requirements. Replaying an assessment
is deterministic; that alone does not establish durable job replay safety.

Two fictional fixtures are positive examples of the workflow boundary, not
representations of the owner's unread emails. No claim of real-email accuracy or
complete unattended intake is made. Existing approval/export validation remains
unchanged. Independent Grok QA and Dot exact-head acceptance plus full hosted CI
are required before accepted development integration.
