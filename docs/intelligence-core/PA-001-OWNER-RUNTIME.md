# PA-001 - Durable Owner Runtime

PA-001 wires the owner Intelligence UI to a separate writable SQLite operational
database. The default path is `intelligence-runtime.db` beside the configured
read-only email database; `EDN_INTELLIGENCE_DB` may select another absolute
path. Sharing the email database is rejected.

Only authority-bound session evidence references and internal proposal payloads
persist. Transcript bodies remain Streamlit session state and are not stored.

The UI exposes capability status and explanations. Proposals remain scoped by
principal, tenant and domain and can be approved-for-future-execution, rejected
or superseded through exact-hash review transitions. Approval requires currently
held evidence references. No executor, external call or production mutation was
added.

Focused development, intelligence and UI validation passes. Full-suite execution
in the available Windows-over-WSL runtime retains the documented missing-tzdata
Calendar failures and one cross-platform filesystem-root assertion.
