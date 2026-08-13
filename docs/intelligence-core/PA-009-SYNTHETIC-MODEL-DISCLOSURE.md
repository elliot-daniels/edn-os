# PA-009-SYNTHETIC — Model Intelligence and Disclosure Boundary

Status: completed synthetic/pre-PA-009 architecture increment. PA-009 remains blocked pending owner approval of a named real provider and genuine evidence disclosure.

## Scope

The provider-neutral boundary accepts an already-authorised `AssembledContext`, evaluates an explicit `DisclosurePolicy`, and fails closed unless authority, security-domain scope and classification ceilings are satisfied. Projection exposes only a bounded source family, title, excerpt, declared freshness state and a one-way provenance digest. Internal context IDs, record references and raw source records are not sent to the provider contract.

`ModelRequest` carries purpose, principal, security domain, projected evidence references, classification, requested capability, bounded output budget and a correlation ID. `ModelResponse` carries typed model assertions, uncertainty, evidence gaps, unsupported assertions and proposal-only actions. Model output is never converted into a verified fact.

Only `SyntheticModelProvider` exists. It requires a synthetic fixture marker, has no credentials or network path, and returns deterministic responses. Provider failure, denied disclosure and invalid requests preserve a local fallback path.

## Security and boundary rules

- Allowed, redacted/projected, denied, classification-ceiling-exceeded, unknown-classification and missing-authority decisions are machine-distinguishable.
- Mixed domains or classifications are rejected as a whole; no partial disclosure is allowed.
- Context and output budgets are deterministic. Obvious synthetic secret/token/raw-payload markers are redacted.
- Provider attribution and disclosed-evidence references remain separate from private EDN provenance.
- Generated actions remain proposal-only and cannot send, modify, approve or execute anything.
- No external provider, live source, SharePoint, remote access, production scheduler or execution capability is activated.

## Future owner decision

Activating PA-009 still requires a named provider, approved disclosure categories and classification ceiling, retention/deletion policy, cost/quota limits, threat model, provider permissions and a separate validation plan. This increment does not grant any of those authorities.
