# Integration inventory and boundaries

The inventory is code/documentation evidence at `0b2a0ba`, not a live tenant audit. No credentials or production data were read. Exact operational runbooks remain linked below.

| Integration | Implemented path | Boundary and current limit |
|---|---|---|
| Historical Outlook archives | memory parser/importers, poc PST extraction comparison | Offline MBOX/directory-derived intake; no direct Outlook COM integration; tool/runtime acceptance separate |
| Outlook legacy connector | connectors/microsoft_outlook | Governed bounded metadata-only default; historical PA-005 scope is separate from Operations |
| Outlook Operations | operations/outlook.py and cli.py, existing GET transport | Explicit plain-text body/attachment-metadata reads; immutable IDs; configured business Inbox only; live acceptance unverified |
| Calendar | connectors/microsoft_calendar | Bounded read-only windows and scope admission; no event writes; current live authority unverified |
| Local Files | connectors/local_files | Approved-root bounded discovery and text/PDF/DOCX ingestion paths; follow PA-002 parser limits; no unrestricted filesystem ingestion |
| SharePoint | connectors/microsoft_sharepoint; installer tooling | Read-only connector and schema diagnostics, plus separately controlled IMS deployment scripts; no deployment authorized here |
| Power Apps / Power Automate | work_capture, config manifests, maker source | Saved scaffold and historical schema evidence; no accepted working submission/flow path; expansion frozen |
| Website intake | separate elliot-daniels/edn-systems-website repository | Handoff describes job-request SharePoint writes; not audited here; preserve source flow; mapping prerequisite for OCT-04 |
| OpenAI pilot | intelligence/model_boundary.py, openai_provider.py and protected stores | Independent guarded PA-009 path; no provider call authorized/run here; not generic cloud triage |
| Grok Bot | proposed repository implementation role | No runtime connector, credentials, grant or live data feed added |
| Streamlit | ui/app.py | Localhost UI, telemetry disabled in documented startup; Operations default and Memory page selector |

## Operations setup contract

`EDN_OPERATIONS_DB` chooses an explicit existing local database for UI; initialization is an explicit CLI action. `EDN_DATA_ROOT` is validated for runtime use. `EDN_MS_TENANT_ID`/`EDN_MS_CLIENT_ID` refer to an already-approved app; application auth additionally requires a secret through the existing credential boundary. `EDN_OPERATIONS_MAILBOXES` enumerates business accounts. Do not put actual values in Git or handover prompts.

Delegated mode verifies the signed-in identity and permits that business mailbox only; Mail.Read plus User.Read is documented. Application mode requires existing approved Mail.Read and mailbox restrictions. SharePoint access does not imply mail access. Cross-tenant accounts need separate authenticated runs into the selected local store, retaining source_account provenance.

Operations window is at most 31 days, at most 100 pages of 50 messages; continuation URLs must retain the exact HTTPS Graph origin/mailbox Inbox resource and original `$select`, `$expand`, `$filter`, `$orderby` and `$top` values. Exactly one nonblank opaque `$skiptoken` or canonical nonnegative ASCII integer `$skip` is allowed; duplicate, omitted, added or changed query fields, raw controls and fragments are rejected before authentication/transport. Attachment metadata is retained, not binaries. Malformed/page-exhausted results are incomplete and exit nonzero; network failures stop intake, with committed Events replay-safe. No delta sync or scheduler exists. A replay never synchronizes subsequent source flag/body changes.

## Handoffs and runbooks

[Operations commands](docs/OPERATIONS-V1.md), [schema launch](docs/SHAREPOINT-SCHEMA-LAUNCH.md), [controlled schema executor](docs/SHAREPOINT-SCHEMA-EXECUTOR.md), [Work Capture source control](docs/work-capture/POWER-APPS-SOURCE-CONTROL-AND-V1-UPDATE.md), [PA-005](docs/intelligence-core/PA-005-BROWSER-AUTHENTICATION.md), [PA-009](docs/intelligence-core/PA-009-OPENAI-PILOT.md).

A development ticket must specify source IDs/fields, authorization boundary, paging/replay/failure behavior and synthetic fixtures. Fresh owner-approved staging/live acceptance is a separate gate. No Microsoft installation, consent grant, permission change or external service edit is part of this audit.
