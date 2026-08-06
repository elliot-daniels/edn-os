# EDN SharePoint Discovery Specification

Status: Implemented; live execution requires separate owner approval
Schema version: 1.0.0
Script version: 1.0.0

## Purpose and scope

IMS-001 produces a metadata-only inventory of an explicitly supplied SharePoint
site. It provides evidence for deciding which EDN Systems OS structures should
be reused or extended. It does not provision the EDN Integrated Management
System (IMS), assess conformity, or create another source of truth.

Within the supplied site URL, and only where the signed-in principal has read
access, the inventory covers:

- site identity, template, locale, timezone, owners, and sharing metadata;
- lists and libraries and their operational settings;
- fields, lookup definitions, choices, defaults, and indexes;
- content types, parents, field links, and list/library associations;
- views, filters, sorts, row limits, and visible fields;
- site and list role assignments, inheritance, principals, and role names;
- discoverable workflow, webhook, formatting, Power Apps, Power Automate, and
  connector references; and
- versioning, retention, record, and sensitivity configuration metadata.

The supplied URL is the discovery boundary. Other site collections, OneDrive,
Teams, Exchange, Purview policy bodies, and tenant-wide configuration are outside
the automatic scope. Each additional site requires a separately approved run.

## Read-only guarantee

The script uses connection and retrieval commands only. It never provisions,
changes, invokes, or removes tenant objects. A static Pester test parses the
PowerShell abstract syntax tree and rejects mutating command verbs and disallowed
web request methods.

The script writes only the user-selected local output directory. It does not:

- change lists, libraries, fields, views, content types, permissions, labels,
  policies, flows, apps, webhooks, files, or list items;
- invoke discovered flows, apps, webhooks, or external connectors;
- download documents, pages, attachments, list-item values, or email bodies;
- enumerate item content or export credentials, tokens, or request headers; or
- treat a permission failure as proof that a section is empty.

Unavailable capabilities are named in `unavailable_sections`; sanitized failures
are recorded in `discovery-errors.json`.

## Authentication and least privilege

PnP.PowerShell is selected because its SharePoint object model exposes list,
field, content-type, view, permission, versioning, formatting, and webhook
metadata more completely than Microsoft Graph alone.

Live use is interactive delegated authentication with the operator's Microsoft
Entra account and MFA. The operator supplies an approved PnP Entra application
client ID. No unattended certificate, client secret, device-code cache, or stored
credential is implemented. Authentication does not grant access beyond the
signed-in principal's existing rights.

The preferred delegated baseline is SharePoint `AllSites.Read`. A tenant-specific
application constrained with `Sites.Selected` and read access to only the approved
site is preferable where the organisation's PnP design supports it. Microsoft
Graph `Sites.Read.All` is needed only if Graph-backed metadata is added later.
Application permissions and unattended authentication are out of scope.

Sharing details, site collection administrators, retention labels, sensitivity
labels, Power Platform associations, or tenant-level settings may be unavailable
without additional read roles or API permissions. Do not broaden access merely
to remove an `unavailable` result; approve each expansion separately.

## Output contract

The user-supplied output directory contains:

```text
SharePointInventory/
  inventory-summary.json
  sites.json
  lists-and-libraries.json
  fields.json
  content-types.json
  views.json
  permissions.json
  automation-references.json
  retention-metadata.json
  discovery-errors.json
```

Every UTF-8 JSON file has this envelope:

| Property | Meaning |
|---|---|
| `schema_version` | Output contract version (`1.0.0`) |
| `script_version` | Producing script version (`1.0.0`) |
| `generated_at_utc` | One ISO 8601 UTC timestamp shared by the run |
| `site_url` | Approved discovery boundary |
| `warnings` | Sorted interpretation warnings |
| `unavailable_sections` | Sorted sections that could not be established |
| `records` | Deterministically sorted metadata records |

`inventory-summary.json` also contains file names and record counts. Errors
contain section, stable target identifier, exception type, and sanitized message;
never a raw request, response body, token, stack trace, or credential object.

### Inventory records

- **Sites:** title, URL, IDs, template/configuration, timezone, locale, language,
  owners, and sharing capability when readable.
- **Lists/libraries:** ID, title, internal/root name, base type, template, URL,
  item count, hidden state, versioning, content approval, checkout, attachments,
  indexed columns, and unique-permission state.
- **Fields:** list ID, display/internal names, GUID, type, required, hidden,
  indexed, lookup metadata, choices, and default value.
- **Content types:** list ID, ID/name, parent ID, attached field IDs/names, and
  list or library association.
- **Views:** list ID, ID/name, URL, default state, row limit, query/filter, sort
  where exposed, and ordered visible fields.
- **Permissions:** scope/ID, inherited or unique state, principal identity/type,
  and sorted roles. Group membership is not expanded.
- **Automation references:** formatting, form customization, workflow, webhook,
  Power Apps, Power Automate, and connector references where directly exposed.
  References are never invoked.
- **Retention metadata:** version limits/settings, deletion settings when exposed,
  information-rights-management state, sensitivity/retention label identifiers,
  and record declaration configuration.

## Normalization and determinism

The normalizer converts GUIDs to lowercase, dates to UTC ISO 8601, and preserves
booleans and numbers as JSON primitives. Unavailable properties are JSON `null`,
not invented defaults. Choices, roles, field names, owners, warnings, unavailable
sections, and records are sorted. Duplicate non-empty stable IDs are rejected.
Properties are emitted in documented order with a terminating newline.

The run timestamp is provenance. Offline tests inject a fixed timestamp when
checking byte-for-byte deterministic output.

## Secrets and exclusions

Secret-like properties are removed recursively, including credentials, passwords,
client secrets, access/refresh/identity tokens, authorization headers, cookies,
and certificate private keys. Bearer-token-shaped strings are redacted even if a
malformed source gives them an unexpected property name.

Excluded by design:

- document/page contents, file bytes, attachments, email bodies, and item values;
- personal profiles, group membership expansion, and item-level permissions;
- authentication caches, cookies, headers, raw service responses, and stack traces;
- licensed standards content and compliance conclusions; and
- full flow definitions, app packages, connector configuration, or invocations.

## Output path, retention, and errors

The output path must be explicit and outside the repository. The script refuses
the repository root or descendants unless `-AllowRepositoryOutput` is deliberately
supplied. Existing inventory files are not overwritten. `.gitignore` patterns are
a secondary safeguard, not authorization to store inventories in Git.

Inventories expose topology, permissions, security settings, and business names.
Store them in an access-controlled EDN location, classify them, retain only as
long as needed for IMS-003 and assurance evidence, and dispose of them under an
approved retention decision. Never commit a live inventory.

Authentication, root-site, path-validation, duplicate-ID, and malformed-response
failures stop the run. Optional-section failures are isolated and recorded so
partial coverage cannot be mistaken for complete coverage. Files are written only
after collection and normalization finish.

## Source, fixtures, and live evidence

| Material | Treatment |
|---|---|
| Script and specification | Versioned source; no tenant data |
| Synthetic fixtures and offline Pester tests | Versioned; invented IDs, URLs, names, and secrets |
| Live tenant inventories | Operational evidence outside Git in approved protected storage |

Synthetic fixtures use reserved example domains and invented identifiers. They
must never be replaced with copied production responses.

## Approval gate and later execution

This implementation has not connected to SharePoint. Before a live run, the owner
must approve the site URL, operator, client ID, permissions, output location,
classification, and retention. After that separate approval, the command is:

```powershell
./installer/Export-EDNSharePointInventory.ps1 `
  -SiteUrl 'https://example.sharepoint.com/sites/EDN' `
  -ClientId '<approved-pnp-entra-application-client-id>' `
  -Tenant 'example.onmicrosoft.com' `
  -OutputDirectory 'C:\EDN-Secure\SharePointInventory\2026-08-06'
```

Example values are placeholders. This documented command is not authorization to
connect to a live tenant.
