# PA-009 — OpenAI Pilot (Activation-Ready, Not Activated)

Status: implementation and synthetic/provider-boundary validation complete. A genuine owner-approved pilot transport occurred but did not yield a locally valid result. Further genuine dispatch remains fresh-preflight and exact-owner-approval gated.

## Proposed model

The proposed pinned model is `gpt-5-mini-2025-08-07`. OpenAI's current model documentation lists GPT-5 mini as supporting the Responses API and structured outputs, with listed text pricing of USD $0.25 per million input tokens and USD $2.00 per million output tokens. These values and model availability must be re-verified immediately before activation. See the [GPT-5 mini model documentation](https://developers.openai.com/api/docs/models/gpt-5-mini).

## Adapter and controls

`OpenAIProvider` implements the existing `ModelProvider` contract using an injected transport. The production transport is standard-library HTTPS; tests use a fake transport and never contact OpenAI. Requests use the Responses endpoint with `store=false`, no tools, no web/file search, no code execution, no uploads and no conversation state. Structured output is parsed into typed `ModelStatement` values and evidence references are checked against the disclosed projection.

The Responses request uses a strict, closed JSON Schema with one explicit
variant for each supported statement kind: model assertion, unsupported
assertion, uncertainty, evidence gap and proposed action. Every variant requires
the complete typed field set and rejects additional properties. Evidence IDs
are enumerated from the actual disclosed projection; unsupported assertions
cannot cite evidence; proposed actions require `proposal_only=true`; and all
other statement types require `proposal_only=false`. Response metadata must
echo the exact EDN request and provider IDs, while the response model must match
the pinned snapshot. The local parser independently enforces these constraints
so invalid provider output fails closed even if it bypasses schema enforcement.

The adapter refuses synthetic requests, disabled providers, missing credentials, disclosure denial, unknown authority, oversized context and local budget exhaustion. Failures normalize to deterministic codes and preserve the caller's local fallback.

## Invalid-response diagnostics

The raw Responses API contract returns generated structured JSON as serialized
text in an assistant `message` output item whose content type is `output_text`.
The SDK-only `output_parsed` convenience and the repository's former synthetic
top-level `structured_output` fixture are not raw HTTP response fields. Synthetic
fixtures now exercise the documented raw envelope, including `object`, `status`,
`output`, message/content and serialized JSON boundaries.

`invalid_response` remains the external failure class. A closed metadata-only
diagnostic pair records the validation stage and an allowlisted reason code for
provider envelope acceptance, identity/model matching, request/provider/model/
policy echoes, Responses output shape and status, structured extraction, JSON
parsing, top-level and statement schemas, statement semantics, disclosed-evidence
references and response ID validity. Exceptions and audit records never include
provider text, parsed statement text, evidence values, prompts or credentials.
Incomplete and refusal responses remain terminal invalid results and are not
retried.

The historical genuine result pre-dates these stage codes, so its exact rejecting
branch cannot be recovered from metadata-only audit. The repository defect was
the collapsed diagnostic boundary and contract-inaccurate successful fixtures;
there is insufficient retained content-free evidence to claim whether the real
response failed at echo, output extraction, JSON/schema, semantic or citation
validation.

## Incomplete-response metadata

Transport metadata and numeric usage are extracted before structured-response
parsing. Audit can therefore retain an allowlisted HTTP status, top-level
Responses status, provider response ID, `input_tokens`, `output_tokens`,
`total_tokens`, input cached tokens, output reasoning tokens and usage-derived
cost even when the result is terminally incomplete or otherwise invalid.
Malformed usage is rejected as a whole rather than partially retained.

Incomplete results preserve external `invalid_response` while distinguishing
`max_output_tokens`, `content_filter`, unknown reasons and missing/malformed
incomplete metadata. The audit separately records whether returned output usage
reached the configured ceiling and whether that ceiling is implicated. Provider
text, refusal text, partial structured output, headers, prompts and evidence are
never copied into diagnostics.

The Responses request now takes `max_output_tokens` directly from
`OpenAIPilotConfig.max_output_tokens`. It previously derived the value as 200
tokens per requested statement; that happened to equal the former 1,000-token
ceiling for five statements but did not faithfully enforce configuration. The
owner-approved pilot ceiling is now 2,000 tokens. Transcript-visible metadata
from the preceding genuine lifecycle recorded
`responses_incomplete_max_output_tokens` at the former ceiling and an actual
usage-derived cost of USD $0.0022085. No unavailable token counts are inferred.
Request construction transmits the configured ceiling directly. Reasoning tokens
remain included in output usage.

## Durable lifecycle audit

Protected dispatch uses an owner-local durable audit by default. The store lives
under `$XDG_STATE_HOME/edn-intelligence-core/provider-audits/`, or
`$HOME/.local/state/edn-intelligence-core/provider-audits/` when XDG state is
unset. Its directory is mode `0700`; canonical per-request journals and lock files
are mode `0600`, effective-user owned, opened without following symlinks and
updated through a locked, fsynced atomic replacement. Each entry is sequence- and
hash-bound to its predecessor, so malformed, truncated, reordered or edited
records fail readback.

The lifecycle records preflight, dispatch admission, transport start, transport
return, retry admission and terminal success/failure before terminal protected
claim destruction wherever sequencing permits. A last state of transport-started
means the outcome is unknown after a crash and never grants replay. Audit records
contain metadata only: exact request/preflight/provider/model/policy binding,
projection counts/categories/size, classification/domain, attempt and transport
state, allowlisted status/failure/validation metadata, numeric usage/cost,
schema/citation outcomes, typed statement counts, retry/fallback outcome and
timestamps. They contain no approval token or provider authority and cannot be
used to reconstruct a projection or dispatch.

Prompts, complete or partial provider response content, structured output text,
statement text, evidence/projection values, source content, credentials,
authorization headers and secrets are prohibited from the durable schema.

## Proposed first-pilot disclosure policy

The source `edn:confidential` classification does not imply external disclosure. A separate `external-model-approved` policy is required. The initial allowlist is limited to projected Calendar metadata, bounded Inbox metadata/sanitised subjects, Local Files metadata/status labels and explicitly approved EDN-owned non-secret engineering labels. Email bodies, arbitrary document content, names/contact details, personal, financial, security-sensitive, Defence/classified, customer-restricted, client and credential material are prohibited by default.

## Credential procedure

An owner must install a least-privilege project credential as `EDN_OPENAI_API_KEY` through the host OS secret store or a protected file outside the repository. The value must never enter Git, configuration JSON, audit records, prompts or logs. Rotation and revocation must be completed before activation. Absence fails closed.

## Local limits

- two total requests per day;
- one successful brief per day;
- one retry per day;
- 4,000 projected context characters;
- 2,000 output tokens;
- AUD 2 estimated daily spend;
- AUD 20 estimated monthly spend.

Budget accounting is owner-local and durable under
`$XDG_STATE_HOME/edn-intelligence-core/provider-budget/` (or the matching
`$HOME/.local/state` fallback). A mode `0600` SQLite database in a mode `0700`
directory is the sole admission authority. `BEGIN IMMEDIATE` atomically checks
and reserves request, retry and estimated spend capacity before credential lookup
or transport. Reservations are never refunded after an unknown crash; successful
completion marks the same reservation rather than creating a second counter.
Lifecycle audit is evidence, while disagreement resolves to the conservative
budget reservation and cannot add authority.

Periods use the existing UTC semantics: calendar day and calendar month. A new
ledger cannot fabricate earlier pilot counters. An explicit owner-attested
opening balance records historical counters as `unknown_pre_ledger`, a digest-
bound AUD $1.00 August carry-in against the unchanged AUD $20 ceiling, and a
next-day `authoritative_from` boundary. Current-day requests remain blocked;
post-cutover daily counters start at zero only after their natural UTC reset. The
carry-in remains charged throughout August and rolls off naturally in September.
Duplicate or modified opening balances fail closed and require distinct owner
authority rather than an in-place reduction.

Every attempted dispatch emits metadata-only audit information: request ID, provider/model, policy, item count, projected categories/size, classification ceiling, decision, status, failure code and usage/cost when available. Prompt and response bodies are not stored.

`max_retries_per_day=1` means one additional transport attempt after an
explicitly retryable pre-valid-result failure; the initial attempt is not a
retry. Retry admission revalidates all protected authority and budget controls
before incrementing request and retry counters. Invalid structured output,
invalid citations and other terminal responses are not retryable. The protected
envelope retains only the normalized initial retryable failure code so a later
terminal refusal cannot overwrite the original transport failure in audit.

## Kill switch and remaining acceptance

`OpenAIPilotConfig.enabled=false` is the default and produces `provider_disabled` without transport dispatch. The deterministic local Daily Intelligence path continues. Before the first genuine request, the owner must accept current provider retention, abuse-monitoring, data-residency, contractual and Australian processing conditions, and explicitly approve the exact model, fields, limits, credential and pilot duration.
