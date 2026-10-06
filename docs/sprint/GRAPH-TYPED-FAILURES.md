# Malformed Graph 200 responses

Calendar and Outlook Graph reads reject invalid JSON/encoding, excessively nested
JSON, non-object envelopes and invalid collection entries as SourceUnavailableError.
Diagnostics contain fixed explanations rather than response content or credentials;
JSON parser exception context is suppressed from displayed tracebacks.
No subsequent page is requested after a malformed collection. Valid projections,
GET-only access, redirect refusal and existing byte/record bounds remain intact.
The separate authentication endpoint parser is unchanged.

Synthetic regression fixtures exercise both transport clients. Operations inherits
Outlook transport decoding, while record-level accounting and lifecycle changes
remain separate work. No production readiness or live Calendar activation claim.
Rollback: revert this change; persisted data and schemas are unchanged.
