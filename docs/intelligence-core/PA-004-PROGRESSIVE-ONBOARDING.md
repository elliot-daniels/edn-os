# PA-004 - Progressive Capability Onboarding

PA-004 adds a deterministic onboarding planner over declared capability manifests
and runtime facts. It performs no discovery probes, authentication, permission
changes or external access.

Each recommendation exposes readiness, its explanation, exact missing steps and
a value score. Ranking weights decision usefulness, recurrence, freshness,
administrative leverage and information density. Record counts and bytes remain
visible capacity inputs but are deliberately excluded from the value score.

For a registered capability that is not ready, the planner can prepare a request
bound to the exact capability, operation, provider, connector, security domain,
scope and declared permissions. Requests begin pending and have an explicit
reject transition. Preparing or displaying a request does not grant authority,
authenticate, or activate a source. Unknown capabilities fail closed without a
fabricated request.

The owner Intelligence UI shows ranked recommendations for its locally composed
registry. Capability profile composition remains explicit and local; a future
persistent inventory must preserve the same declaration and authority boundary.
