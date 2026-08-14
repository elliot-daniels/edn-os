# PA-009 — OpenAI Pilot (Activation-Ready, Not Activated)

Status: implementation and synthetic/provider-boundary validation complete. No genuine EDN evidence has been sent to OpenAI. PA-009 remains owner-gated at the first real request.

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

## Proposed first-pilot disclosure policy

The source `edn:confidential` classification does not imply external disclosure. A separate `external-model-approved` policy is required. The initial allowlist is limited to projected Calendar metadata, bounded Inbox metadata/sanitised subjects, Local Files metadata/status labels and explicitly approved EDN-owned non-secret engineering labels. Email bodies, arbitrary document content, names/contact details, personal, financial, security-sensitive, Defence/classified, customer-restricted, client and credential material are prohibited by default.

## Credential procedure

An owner must install a least-privilege project credential as `EDN_OPENAI_API_KEY` through the host OS secret store or a protected file outside the repository. The value must never enter Git, configuration JSON, audit records, prompts or logs. Rotation and revocation must be completed before activation. Absence fails closed.

## Local limits

- two total requests per day;
- one successful brief per day;
- one retry per day;
- 4,000 projected context characters;
- 1,000 output tokens;
- AUD 2 estimated daily spend;
- AUD 20 estimated monthly spend.

Every attempted dispatch emits metadata-only audit information: request ID, provider/model, policy, item count, projected categories/size, classification ceiling, decision, status, failure code and usage/cost when available. Prompt and response bodies are not stored.

## Kill switch and remaining acceptance

`OpenAIPilotConfig.enabled=false` is the default and produces `provider_disabled` without transport dispatch. The deterministic local Daily Intelligence path continues. Before the first genuine request, the owner must accept current provider retention, abuse-monitoring, data-residency, contractual and Australian processing conditions, and explicitly approve the exact model, fields, limits, credential and pilot duration.
