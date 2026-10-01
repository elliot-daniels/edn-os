# Bounded schema failure diagnostics

The initial diagnostic change described below added observability only.
The subsequent column-validation correction is documented in the final section. The consumed run
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

## Historical acceptance analysis at 3b8b838 (superseded below)

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

## Column validation isolation after acd2e9c

The consumed September 29 run's column_limit_or_shape proves only that the
collection guard rejected the parsed object. It does not identify which branch,
the column count or any live column's schema. The raw response was not retained.
No live replay or artifact/deadline modification was performed.

### Exact old guard and replacement

| Old condition | New reason |
| --- | --- |
| value absent (get returned None) | columns_value_missing |
| value is not a list, including null | columns_value_not_array |
| list length is zero | columns_empty |
| list length exceeds 100 | columns_limit_exceeded |

There were no other column_limit_or_shape branches. A non-object top level
previously failed earlier as invalid_object; it now reports
columns_top_level_not_object for a columns response. Exactly 100 always passed.
The local 1..100 bound still matches $top=100. No limit was raised.

Previously, unexpected ordinary top-level properties were discarded; this remains
true. Operational properties and continuation are rejected recursively before
schema validation. Required fields, malformed records, facet count/shape and lookup
configuration were checked sequentially inside _column, never by collection-wide
prevalidation. Each accepted record incremented validated_records. Duplicate
identity detection followed the loop. Thus the consumed combined error cannot
have come from any of those record-level conditions.

### Current record policy and safe diagnostics

Each record requires id/name/displayName and Boolean required/readOnly/hidden.
Missing fields report column_required_field_missing; invalid/null scalars or
invalid UUID report column_required_field_type_invalid. Non-objects report
column_record_not_object. Multiple populated approved facets report
column_type_facet_ambiguous. Populated geolocation/thumbnail/contentApprovalStatus
report column_type_facet_unsupported. Unreviewed column properties fail as
column_unexpected_shape (their names/values are never copied into diagnostics).
Known unsolicited metadata is discarded. Invalid facet objects or selected
nested property types, and incomplete/invalid lookup identity, report
column_facet_shape_invalid.

Diagnostics add a zero-based column_ordinal and a closed column_facet classification
(approved facet, unavailable, ambiguous, unsupported, or null). No failed column
name, display name, ID, choices, formulas, arbitrary property name or error text
is copied into the failure audit. validated_records counts successful preceding
columns; partial columns are not persisted on failure.

### Documented Graph compatibility correction

Microsoft's [columnDefinition documentation](https://learn.microsoft.com/en-us/graph/api/resources/columndefinition?view=graph-rest-1.0)
explicitly allows basic properties without populated type facets for field types
not represented by the API. The previous exactly-one-facet rule rejected these
legitimate definitions. A zero-facet record with valid base fields is now retained
with type_status=unavailable, including when selected facets are null. This is an
explicit coverage limitation, not inferred text type or adapter eligibility.
Populated unsupported/unknown facets still fail. This compatibility defect is
independent of the consumed collection-level failure, whose exact cause is unknown.

The approved projection is unchanged. The documentation also says list/site
responses omit hyperlinkOrPicture and term; no requirement that these be populated
has been added. If present, they retain their existing narrow type checks.
The review covers all eleven existing facets:
[text](https://learn.microsoft.com/en-us/graph/api/resources/textcolumn?view=graph-rest-1.0),
[number](https://learn.microsoft.com/en-us/graph/api/resources/numbercolumn?view=graph-rest-1.0),
[dateTime](https://learn.microsoft.com/en-us/graph/api/resources/datetimecolumn?view=graph-rest-1.0),
[choice](https://learn.microsoft.com/en-us/graph/api/resources/choicecolumn?view=graph-rest-1.0),
[boolean](https://learn.microsoft.com/en-us/graph/api/resources/booleancolumn?view=graph-rest-1.0),
[lookup](https://learn.microsoft.com/en-us/graph/api/resources/lookupcolumn?view=graph-rest-1.0),
[personOrGroup](https://learn.microsoft.com/en-us/graph/api/resources/personorgroupcolumn?view=graph-rest-1.0),
[currency](https://learn.microsoft.com/en-us/graph/api/resources/currencycolumn?view=graph-rest-1.0),
[calculated](https://learn.microsoft.com/en-us/graph/api/resources/calculatedcolumn?view=graph-rest-1.0),
[hyperlinkOrPicture](https://learn.microsoft.com/en-us/graph/api/resources/hyperlinkorpicturecolumn?view=graph-rest-1.0),
[term](https://learn.microsoft.com/en-us/graph/api/resources/termcolumn?view=graph-rest-1.0).
Existing nested projections match the reviewed scalar types; formula and unrelated
nested configuration remain discarded. Lookup listId/columnName remain mandatory
for supported relationship mapping; targets are never followed.

Only public documentation was read. No Microsoft authentication, tenant/Graph/
SharePoint access or live schema execution occurred. Existing retention deadlines,
including 2026-10-06T05:43:41.717265Z, are unchanged.

Next owner decision: authorize at most one fresh projects_schema_diagnostic run
(site, Projects identity, Projects columns), same projection/cap/storage/retention,
no retry and no Clients/Actions. This document does not authorize that run.

Validation for this correction: 297 focused tests passed; full suite 912 passed,
92 failed, 1 skipped. Failure identities exactly equal executive-baseline.xml:
zero new and zero missing baseline failures. Ruff, strict Linux-target mypy
(129 source files) and git diff --check passed. Security baseline checks were
not weakened. The tests are synthetic; no operational sources were accessed.
