# Bounded schema failure diagnostics

This local change adds observability only. The consumed run
run-b2d4d98692e44bcb8acb62a5ff791353 cannot be reconstructed: Request 3's status,
body and precise rejection were not retained. No live cause is asserted.

## Confirmed local diagnostic defects

Transport and executor blanket catches erased safe error codes. The decoder
caught SchemaInspectionError as ValueError, masking pagination/prohibited-content
reasons. These are fixed without relaxing schema acceptance. Lookup/column ID
and missing-property errors now have safe classifications instead of unlabelled
ValueError/KeyError. Unknown exceptions never contribute their text.

## Audit schema

Each request retains ordinal, approved purpose, fixed endpoint class and UTC
attempt time. Arbitrary URL strings are no longer stored in request audit entries.
Diagnostic fields: stage; network_dispatch_started/completed; response_received;
http_status; bounded content_type (application/json, text/html, text/plain, other);
response_bytes capped at MAX_BYTES+1; UUID-only request_id/client_request_id;
json_parsed; validated_records; allowlisted graph_error_code; failure_category;
failure_reason; pagination_rejected, redirect_rejected, prohibited_content_rejected.

Dispatch started means the client began attempting the request, not proof the
server received it. Dispatch completed means connection.request returned. HTTP
receipt is separately recorded. Unknown observations remain null/false. Stage
is prepared, dispatch, response_headers, response_body, response_parsing,
content_guards, schema_validation or verified. Synthetic transports do not claim
real network dispatch. The whole request remains unverified after any rejection.

Categories distinguish authentication_authorization, transport, http_status,
graph_error, malformed_json, unexpected_response_shape, prohibited_content,
pagination, redirect, unsupported_schema_facet, projection_field_incompatibility,
identity_verification, persistence_audit and internal_executor. Reason codes are
a closed map in schema_executor.FAILURE_CATEGORIES. Graph codes are a separate
small fixed vocabulary; unrecognized codes become other. No Graph error message,
raw body, cookies, auth header, token or stack trace is serialized. Request IDs
are accepted only as UUIDs. Redirect targets are never recorded/followed.

The existing budget, sequencing, no-replay marker, two independent request
allowlists, storage guards, retention and manifest hashes remain in force.
If storage itself fails, audit_write_failed is raised without OS error text;
persisting that failure cannot be guaranteed on the failed storage medium.

## Request 3: local acceptance analysis, not a live diagnosis

The request still selects id,name,displayName,required,readOnly,hidden,text,number,
dateTime,choice,boolean,lookup,personOrGroup,currency,calculated,hyperlinkOrPicture,
term and uses $top=100. No projection or schema policy was changed.

- All six identity/flag fields must exist, with correct types and UUID column ID.
- Exactly one recognized non-null facet is required. Zero facets, only an unknown
  type, or multiple recognized facets fail. Null facets do not count.
- Hidden/system columns receive the same validation. Missing selected type facets
  on system columns could therefore fail. Hidden itself is not a rejection.
- Lookup needs UUID listId and nonempty columnName; missing/invalid values fail.
  No target is traversed. Person and calculated facets use the existing narrow
  projection; formulas and unknown nested properties are discarded.
- Known properties with null/wrong values fail. Unknown ordinary properties are
  discarded, not categorically rejected. Operational keys are rejected recursively.
- term is in the local request/validator vocabulary. Whether this exact v1.0
  projection is accepted for the live list remains unverified; HTTP 400 and a safe
  Graph error code would distinguish remote rejection, not prove which field caused it.
- Empty/malformed collections, over 100 columns, duplicate names/IDs, nextLink or
  deltaLink fail closed. Exactly 100 without continuation is accepted and cap flagged.
- HTTP/authorization, content type/encoding, response-size, transport, malformed
  JSON and duplicate JSON keys remain possible distinct failure classes.

A safe error code such as invalidRequest alone does not prove projection
incompatibility. No claim is made that an unsupported live facet was observed.

## Smallest proposed live diagnostic

Prefer site identity -> Projects identity -> Projects columns -> STOP, maximum
three GETs in one fresh run, same projection and guards, no retry. Use the explicit tested projects_schema_diagnostic mode; the default full mode
still plans seven on success. Do not rely on manually interrupting a full run. No authentication or retry is authorized here.

Validation: 222 focused tests passed; full suite 837 passed, 92 failed, 1 skipped.
The failure identities exactly match executive-baseline.xml and
unique-storage-full.xml. Ruff, strict Linux-target mypy (129 files) and whitespace
checks passed. Zero Microsoft access during this local change.
