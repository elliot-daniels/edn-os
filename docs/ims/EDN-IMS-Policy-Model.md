# EDN IMS Policy and Configuration Model

Status: Design example only; not connected to production behaviour  
Date: 2026-08-09

## Boundary

The future policy layer should validate configuration and gate operations. It
must not become an approval authority. EDN-specific values belong in tenant
configuration; reusable validation, discovery, provenance and human-authority
rules belong in the Business OS platform.

## Proposed configuration hierarchy

```text
platform-policy.schema.json       reusable contract and validation rules
tenant/edn/organisation.yaml      name, locale, terminology and domains
tenant/edn/governance.yaml        classification, retention and authorities
tenant/edn/sharepoint.yaml        site/list/library/field identity mapping
tenant/edn/risk.yaml              matrix, thresholds and review rules
tenant/edn/record-types.yaml      documents, obligations and event types
tenant/edn/metrics.yaml           measures, targets and dashboard configuration
```

Secrets, credentials, tokens, live inventories and generated assessments are
never valid configuration values. Production configuration should live in a
separately approved location with environment overlays; this task creates no
runtime configuration.

## Example machine-readable configuration

```yaml
schema_version: "0.1-design"
organisation:
  key: edn
  display_name: EDN Systems
  locale: en-AU
  timezone: Australia/Adelaide

terminology:
  risk_register: Risks and Opportunities
  controlled_documents: Controlled Documents
  assurance_records: Assurance, Events and Findings

domains:
  - quality
  - whs
  - information_security
  - project_delivery
  - commercial_client
  - assurance

classifications:
  default_operational: EDN Internal
  discovery_output: EDN Confidential
  choices:
    - Public
    - EDN Internal
    - EDN Confidential
    - Restricted

discovery:
  mode: read_only_metadata
  require_explicit_site_boundary: true
  authentication: interactive_mfa
  require_named_human_approver: true
  allow_unattended_credentials: false
  unknown_is_absent: false
  git_output_allowed: false
  output:
    require_explicit_protected_path: true
    no_clobber: true
    require_separate_backup: true
    require_sha256_manifest: true
  exclusions:
    - credentials
    - tokens
    - request_headers
    - file_contents
    - list_item_values
    - email_bodies
    - stack_traces

retention:
  discovery_evidence:
    period_months: 12
    disposal_conditions:
      - implementation_decisions_complete
      - audit_and_troubleshooting_complete
      - retention_period_expired
    backup_inherits_policy: true
  operational_records:
    status: owner_or_specialist_confirmation_required

authority:
  risk_acceptance: human_only
  document_approval: human_only
  finding_closure: human_only_when_required
  exceptions: human_only
  conformity_claims: prohibited_for_automation
  essential_eight_maturity_claims: require_separate_approval_and_evidence

ai:
  allowed:
    - suggest_classification
    - suggest_mapping
    - draft_summary
    - flag_stale_records
  prohibited:
    - fabricate_evidence
    - accept_risk
    - approve_documents
    - close_governance_records
    - determine_legal_reportability
    - claim_certification_or_conformity
  require_source_reference: true
  require_human_review_state: true

risk:
  scale: likelihood_x_consequence_1_to_5
  automatic_calculation_allowed: true
  acceptance_requires_approval_record: true
  thresholds:
    low: [1, 4]
    moderate: [5, 9]
    high: [10, 16]
    extreme: [17, 25]
  acceptance_authorities:
    status: owner_confirmation_required

sharepoint:
  authoritative_objects:
    projects: {display_name: Projects, identity: preserve_live_guid}
    actions: {display_name: Actions, identity: preserve_live_guid}
    assets: {display_name: Assets, identity: preserve_live_guid}
    controlled_documents:
      display_name: SOPs & Templates
      navigation_label: Controlled Documents
      url_policy: preserve
  mutation_defaults:
    additive_fields_only: true
    rename_internal_fields: false
    delete_existing_fields: false
    test_site_first: true
    require_dependency_review: true
    require_rollback_plan: true
    require_named_implementation_approval: true

provenance:
  require_schema_version: true
  require_source_identifier: true
  require_source_url_where_available: true
  require_timestamps: true
  require_hashes_for_exported_evidence: true
```

## Validation semantics

- `human_only` means software may prepare a draft but cannot set the authoritative
  approved/accepted state or impersonate the approver.
- `unknown_is_absent: false` is fail-closed: unavailable evidence remains an
  explicit unknown and blocks destructive or assurance conclusions.
- Authority maps contain roles or named identities in tenant configuration, not
  executable code.
- Retention values are record-class specific. The approved 12-month rule applies
  to discovery evidence only and must not silently become the operational IMS
  retention schedule.
- Display terminology is configurable. Stable keys and internal field names are
  not translated or renamed after deployment.

## Future validation requirements

The eventual policy engine should validate schema versions, choice references,
authority references, risk thresholds, output path class, prohibited secrets,
lookup targets and approval gates. It should emit a proposed change plan and
never execute tenant mutation unless a separate deployment command and approval
record explicitly authorise it.

