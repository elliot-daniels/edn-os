# PA-007 - Freshness-aware Daily Intelligence

## Outcome

PA-007 turns already-authorised Calendar, Outlook Inbox, Local Files, historical
email and knowledge evidence into a deterministic owner-facing brief. Composition
receives only the bounded `AssembledContext`; it cannot retrieve, authenticate,
mutate a source, invoke a model, send a message or execute an action.

The canonical sections are:

1. Executive summary
2. Immediate attention
3. Today / upcoming commitments
4. Recent communications / commitments
5. Project / operational context
6. Risks, gaps and stale evidence
7. Suggested internal actions or decisions

Every section is always present. Empty evidence does not mean “nothing to
report”: expected Calendar, Inbox and Local Files absences are explicit typed
gaps and the brief states that completeness is unknown.

## Evidence and epistemic types

`ContextEvidence` retains its Core provenance and now optionally carries a
declared source timestamp plus its timestamp kind. The timestamp pair must be
complete and timezone-aware. It never comes from retrieval order.

Brief items reuse the existing `StatementKind` vocabulary. Facts require evidence
IDs; unknown/gap items cannot claim evidence; inferences remain labelled; and
suggested actions are `proposal_only`. Suggestions explicitly prohibit sending,
source mutation and execution. Existing exact-hash action proposals remain a
separate internal review lifecycle and no executor is introduced.

## Freshness model

Freshness is evaluated at the caller-supplied timezone-aware brief time against
an exact capability policy:

| Capability | Declared timestamp | Current | Ageing | Stale |
|---|---|---:|---:|---:|
| `calendar.search` | event end | up to 1 day old (including bounded upcoming events) | over 1 through 7 days | over 7 days |
| `outlook.search` | message received | up to 1 day | over 1 through 7 days | over 7 days |
| `local-files.search` | file modified | up to 7 days | over 7 through 30 days | over 30 days |
| `email.retrieve` | email sent | up to 7 days | over 7 through 30 days | over 30 days |
| `knowledge.retrieve` | declared source time when available | up to 7 days | over 7 through 30 days | over 30 days |

A missing timestamp or missing exact capability policy is `unknown_freshness`.
Stale and unknown-freshness evidence is visible in risks/gaps but cannot enter
Immediate attention or Suggested internal actions.

## Deterministic ranking

Ranking uses only declared factors:

```text
freshness × 5
+ decision usefulness × 4
+ distinct corroborating source families × 3 (bounded)
+ recurrence × 2
+ provenance confidence × 2
```

Source value factors are fixed in code on a one-to-five scale. Corroboration is
awarded only for an exact normalised title shared by distinct source families;
it does not merge records or turn an inference into a fact. Stable context ID is
the final tie-breaker. Retrieval score, record count, bytes and source volume do
not contribute to brief rank.

## Security and validation

- Permission and capability decisions still occur before every adapter call.
- Context assembly still rejects domain or classification mismatches before
  composition.
- Evidence retains source-owned references under `EDN / edn-local /
  confidential` when that is the request boundary.
- Automated tests use injected synthetic adapters only. They perform no live
  authentication, Microsoft Graph, filesystem, SharePoint or model call.
- PA-005 permissions, Inbox scope, filesystem scope, classifications, retention
  and the protected owner activation pack are unchanged.
- No SharePoint adapter is added to the expected owner brief source set.

Synthetic acceptance covers fresh Calendar, ageing/stale evidence, current Inbox
metadata, Local Files evidence, unavailable/missing sources, weak or undated
evidence, exact-title mixed-source corroboration, volume-independent ranking and
non-executing suggestions.

## Deliberate limits

The brief is deterministic evidence triage, not semantic business-state
extraction. It does not infer owners, deadlines, commitment status or business
truth from weak evidence. Exact-title corroboration is intentionally conservative.
Owner usefulness review remains a human product judgement; passing repository
validation does not establish that judgement or grant live/source authority.
