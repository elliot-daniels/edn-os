# PA-006 - Synthetic Business OS SharePoint Retrieval

PA-006 adds a bounded, read-only Microsoft SharePoint connector contract and a
source-neutral Intelligence adapter. The connector operates only through an
injected client protocol. No HTTP implementation, authentication, token handling,
live content access, schema deployment or mutation method exists.

Configuration binds an exact tenant, site, list, allowed field projection,
security field/value, Core security domain, classification and freshness window.
Capabilities are limited to `sharepoint.search` and `sharepoint.verify` with the
site-scoped `Sites.Selected` permission declaration.

Admitted Business OS records retain the exact projected field names, SharePoint
item identity, list/source identity, security value, modified and retrieval
timestamps, item version/eTag and source URL. Items whose security value does not
match the configured value are filtered before evidence creation. Content,
version-history, drive-item and permission payload expansion fails closed.

All automated validation uses an in-memory synthetic client. Live SharePoint
content remains owner-blocked, and existing IMS deployment/mutation tooling is
not imported or reachable from this connector.
