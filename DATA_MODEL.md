# Implemented data model

Snapshot: Operations parent `0b2a0ba`. SQL and typed models in source are authoritative for implemented fields. This inventory distinguishes logical specifications from deployed/local runtime schemas; no migration was executed.

## Historical Memory

`src/edn/memory/models.py::EmailRecord` contains source_record_key, folder_path, subject, sender, recipient tuples (to/cc/bcc), sent_at, received_at, message_id and body_text. `memory/storage.py` defines:

| Table | Identity / relationships | Stored state |
|---|---|---|
| emails | integer id; globally unique source_record_key in this database | folder, subject, sender, serialized recipient fields, optional timestamps/message_id, body_text |
| email_import_status | source_id primary key | status, observed_at |
| emails_fts | FTS5 external content=emails, content_rowid=id | subject, sender, body_text; insert trigger maintains index |

This is not the source_archives/import_runs/messages/attachment schema proposed in `docs/ARCHITECTURE.md`. Do not write a query or migration assuming those tables exist. Source identity and folder are retained, but do not claim all proposed archive fingerprint/run provenance and sensitivity fields are implemented in EmailRecord. Parser/importer contracts define actual key generation; do not change key semantics without replay tests.

## Knowledge graph

`knowledge_graph/persistence.py` defines knowledge_entities (unique entity_type/normalized_name), knowledge_entity_occurrences (entity_id/source_record_key/field_name), knowledge_relationships (unique subject/predicate/object), knowledge_relationship_sources (relationship_id/source_record_key) and knowledge_extraction_state (singleton checkpoint with last_email_id/rule_version). Entity/relationship sources refer to email source keys. These are extracted claims with evidence, not an authoritative CRM. Rule-version mismatch is an explicit boundary.

## Operations Event

`operations/models.py::Event` is a frozen dataclass. Required: source, source_account, external_id, occurred_at, direction, event_type; identity strings are nonempty, timestamps timezone-aware. UTC ISO strings are serialized. Optional/default state includes local UUID id, created_at, parties, subject, body, attachment metadata, client_id/project_id/job_id, ai_summary, ai_actions, needs_action and raw_payload.

| Physical column in operations_events | Constraint / purpose |
|---|---|
| id | text primary key, local Event identity |
| source, source_account, external_id | unique composite replay identity |
| occurred_at | UTC serialized timestamp, newest-first index with id |
| needs_action | integer snapshot flag |
| client_id, project_id, job_id | optional opaque links, no local catalogue/FK enforcement |
| payload | complete serialized Event JSON, including source body/raw provenance |

First-write-wins inserts return the existing Event on replay. Later source flags/body changes do not update stored content. No cross-mailbox deduplication, attachment binaries or AI processing is implemented. Supported types are email/job_request/sms/whatsapp/call/voicemail/note/job_update; only Outlook email has an intake adapter. Store is isolated from Memory and read-only in the Inbox UI. OCT-05 proposes separate local triage state without mutating source snapshots.

## Governed evidence and other stores

`core/references.py` defines SourceRef, UniversalRecordRef and EvidenceRef; `core/security.py` binds authority identity/domain/classification. Do not equate provider-native opaque IDs with EDN authority IDs. Session continuation, proposal hashes and evidence freshness are separate controls (`intelligence/session.py`, `actions.py`, `temporal.py`). Runtime sessions/proposals, worker jobs, protected provider budget/preflight/result and delegation stores each own their schema and access rules. They are not tables in the Operations database by implication.

Work Capture models (`work_capture/models.py`) include typed capture, actor/entity/evidence references, project defaults and billing/outcome enums. SharePoint IMS target schema and relationships remain documented in [target schema](docs/ims/EDN-IMS-Target-Schema.md) and [relationship model](docs/ims/EDN-IMS-Relationship-Model.md); historical schema activation is not current source-content integration. The separate website's job-request mapping must be inspected and agreed before OCT-04.

## Evolution rules

Every schema change needs compatibility, replay, upgrade and rollback evidence using synthetic data. Back up real stores only through an approved owner process. Do not merge Memory and Events, invent business relationship constraints, regenerate frozen Power Apps hashes or relabel security identities as incidental cleanup.
