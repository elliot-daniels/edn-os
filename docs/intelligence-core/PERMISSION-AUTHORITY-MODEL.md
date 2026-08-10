# Permission and Authority Model v0.1

## Decision model

Permissions answer whether context or an operation may be used. Authority answers
who may approve or execute it. Authentication proves identity to a source; it is
not permission or authority.

Decision outcomes:

- `always_allowed` within an explicit rule and scope;
- `allowed_within_scope`;
- `approval_required`;
- `temporarily_approved` until an expiry/usage limit;
- `prohibited`;
- `indeterminate` when evidence/configuration is missing (fail closed).

## Policy request

Every decision evaluates:

```text
principal + tenant + security domain + permitted purpose
+ capability + operation + target/source scope
+ data classification + sensitivity + provider/location
+ requested duration/volume + prior approval + current time
```

The result includes outcome, effective scope, obligations, approval type,
reason/rule ID, expiry, prohibited downstream uses and audit ID.

## Operation vocabulary

`discover`, `read`, `search`, `ingest`, `sync`, `use_local_reasoning`,
`use_cloud_ai`, `draft`, `write_internal`, `approve`, `execute`, `delete`,
`share_external`, `install_connector`, `change_permission`.

Broad `write` permission never implies delete, send, publish or approve.

## Human authority boundaries

The system may prepare evidence and drafts. A human remains authoritative for
risk acceptance, controlled-document approval, governed closure, external
communications, financial commitments, permission grants, connector installation
and any operation a tenant policy marks human-only. The audit record stores the
human principal, exact plan/hash, decision, timestamp, conditions and expiry.

## Temporary approval

A temporary approval binds to exact capability version, source/target scope,
operation, manifest/plan hash, principal, purpose, window, usage count and output
location. Scope drift or expiry returns `approval_required`; it is never silently
renewed.

## Alpha policy storage

Use versioned tenant configuration for rules and a local append-only decision
ledger for approvals/denials. Secrets remain in OS/provider credential stores.
The engine initially performs deterministic rule evaluation—no AI policy judge.

## Example policies

```yaml
- id: edn-email-local-search
  principal: owner
  domains: [EDN]
  operations: [search, use_local_reasoning]
  capability: search_email_memory
  decision: allowed_within_scope

- id: personal-sms-business-deny
  domains: [PERSONAL]
  purposes: [employee_query, business_analytics]
  decision: prohibited

- id: sharepoint-schema-write
  domains: [EDN]
  capability: create_sharepoint_optional_field
  operations: [execute]
  decision: approval_required
  bind_approval_to: [site, manifest_hash, plan_hash, window]
```

## Enforcement points

Policy is checked before discovery, before retrieval, before context assembly,
before provider dispatch, before job start/resume and immediately before action
execution. Evidence returned from a connector is tagged with its domain and
purpose constraints so it cannot be reused in a broader session.

## Required tests

- deny PERSONAL evidence in EDN employee context;
- deny cloud AI for restricted context;
- reject expired/altered Plan approvals;
- distinguish draft from execute;
- prohibit delete despite read/write-internal permission;
- fail closed on missing classification or principal;
- preserve reason/audit ID for allow and deny; and
- ensure an administrator's source permission does not create platform authority.

