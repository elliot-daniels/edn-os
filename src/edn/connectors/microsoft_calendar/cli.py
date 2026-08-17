"""Explicit post-approval live read-only Calendar validation command."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from edn.connectors import ConnectorRequest
from edn.connectors.microsoft_calendar import (
    CalendarConfig,
    CalendarRetrievalResult,
    CalendarScopeMode,
    CalendarWindow,
    DeviceCodeCredential,
    MicrosoftCalendarConnector,
    MicrosoftGraphCalendarClient,
)
from edn.core import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    Classification,
    PermissionEvaluator,
    PermissionOutcome,
    PermissionRequest,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    evaluate_capability_use,
)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    output = Path(args.output)
    if not output.parent.is_dir() or output.exists():
        parser.error("output parent must exist and output must be a no-clobber file")
    domain = SecurityDomain("EDN", "EDN Systems", tenant_id=args.tenant)
    classification = Classification("edn", "confidential", "EDN Confidential", rank=2)
    mode = CalendarScopeMode(args.scope_mode)
    config = CalendarConfig(
        args.tenant,
        args.account,
        args.calendar_id,
        args.calendar_name,
        "Australia/Adelaide",
        domain,
        classification,
        mode,
        args.required_category,
    )
    connector = MicrosoftCalendarConnector(
        config,
        MicrosoftGraphCalendarClient(DeviceCodeCredential(args.tenant, args.client_id)),
    )
    request = _authorized_request(connector, domain, classification, args.window)
    retrieval = connector.search_events(
        request,
        window=CalendarWindow(args.window),
        now=datetime.now(UTC),
        limit=args.limit,
    )
    result = build_validation_report(
        retrieval,
        account=args.account,
        calendar_id=args.calendar_id,
        domain=domain,
        classification=classification,
        window=args.window,
    )
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                **retrieval.counts_dict(),
                "event_body_reads": 0,
                "calendar_mutations": 0,
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


def build_validation_report(
    retrieval: CalendarRetrievalResult,
    *,
    account: str,
    calendar_id: str,
    domain: SecurityDomain,
    classification: Classification,
    window: str,
) -> dict[str, object]:
    """Serialize counts and admitted evidence; rejected objects are unavailable."""
    return {
        "operation": "read-only-calendar-validation",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "account": account,
        "calendar_id": calendar_id,
        "domain": domain.to_dict(),
        "classification": classification.to_dict(),
        "window": window,
        "permission": "Calendars.Read",
        **retrieval.counts_dict(),
        "rejection_reasons": retrieval.rejection_reasons_dict(),
        "event_body_reads": 0,
        "calendar_mutations": 0,
        "events": [item.to_dict() for item in retrieval.events],
    }


def _authorized_request(
    connector: MicrosoftCalendarConnector,
    domain: SecurityDomain,
    classification: Classification,
    window: str,
) -> ConnectorRequest:
    principal = PrincipalContext(
        "approved-operator", domain.tenant_id or "edn", frozenset({domain}), True
    )
    purpose = Purpose("ic009-live-validation", "Approved IC-009 validation")
    scope = (connector.config.calendar_id, f"window:{window}")
    permission_request = PermissionRequest(
        "ic009-live-policy",
        principal,
        purpose,
        "calendar.search",
        "search",
        domain,
        classification,
        scope,
    )
    manifest = next(
        item
        for item in connector.manifest.capabilities
        if item.capability_id == "calendar.search"
    )
    registry = CapabilityRegistry()
    registry.register(
        manifest,
        CapabilityRuntimeState(
            CapabilityStatus.READY, AuthenticationStatus.VALID, health="live-approved"
        ),
    )
    policy = PermissionEvaluator(
        PolicySet(
            "ic009-live-approval",
            "1",
            (
                PolicyRule(
                    "ic009-exact-read",
                    PermissionOutcome.ALLOWED_WITHIN_SCOPE,
                    "Owner-approved read-only live validation.",
                    principal_ids=frozenset({principal.principal_id}),
                    domain_ids=frozenset({domain.domain_id}),
                    purpose_ids=frozenset({purpose.purpose_id}),
                    capability_ids=frozenset({"calendar.search"}),
                    operations=frozenset({"search"}),
                    resource_scopes=frozenset(scope),
                ),
            ),
        )
    )
    decision = evaluate_capability_use(
        registry, policy, permission_request, now=datetime.now(UTC)
    )
    return ConnectorRequest(
        "ic009-live-request",
        "ic009-live-correlation",
        principal,
        purpose,
        domain,
        classification,
        "calendar.search",
        "search",
        decision,
        scope,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("validate-live", nargs="?")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--calendar-id", required=True)
    parser.add_argument("--calendar-name", required=True)
    parser.add_argument(
        "--scope-mode",
        choices=tuple(item.value for item in CalendarScopeMode),
        required=True,
    )
    parser.add_argument("--required-category")
    parser.add_argument(
        "--window", choices=tuple(item.value for item in CalendarWindow), required=True
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
