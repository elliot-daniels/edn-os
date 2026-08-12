"""Bounded PA-005 preflight and owner-invoked live Microsoft validation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edn.connectors import ConnectorRequest
from edn.connectors.microsoft_calendar import (
    BrowserInteractiveCredential,
    CalendarConfig,
    CalendarScopeMode,
    CalendarWindow,
    MicrosoftCalendarConnector,
    MicrosoftGraphCalendarClient,
)
from edn.connectors.microsoft_outlook import (
    MailScopeMode,
    MailWindow,
    MicrosoftGraphOutlookClient,
    MicrosoftOutlookConnector,
    OutlookConfig,
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

TENANT_ID = "aae6ab79-45eb-4829-a04f-595becdb936d"
CLIENT_ID = "2381e4f6-44bc-4697-ad64-e86513cb9dee"
ACCOUNT_ID = "elliot@ednsystems.com.au"
CORE_TENANT_ID = "edn-local"
SCOPES = ("User.Read", "Calendars.Read", "Mail.Read")
TIMEZONE = "Australia/Adelaide"
CATEGORY = "EDN"
LIMIT = 25


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    _validate_output(output)
    if args.command == "preflight":
        print(json.dumps(_preflight(output), sort_keys=True))
        return 0
    report = _validate_live()
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), **report["counts"]}, sort_keys=True))
    return 0


def _preflight(output: Path) -> dict[str, object]:
    """Validate fixed boundaries without opening a credential or source."""
    BrowserInteractiveCredential(TENANT_ID, CLIENT_ID, ACCOUNT_ID, SCOPES)
    return {
        "status": "ready-for-owner-go",
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "account_id": ACCOUNT_ID,
        "delegated_permissions": list(SCOPES),
        "calendar": {"id": "default", "window": "this-week", "limit": LIMIT},
        "mail": {"folder": "inbox", "window": "last-7-days", "limit": LIMIT},
        "category": CATEGORY,
        "output": str(output),
        "network_calls": 0,
        "source_reads": 0,
    }


def _validate_live() -> dict[str, Any]:
    domain = SecurityDomain(
        "EDN", "EDN Systems", tenant_id=CORE_TENANT_ID, owner_id="local-owner"
    )
    classification = Classification(
        "edn", "confidential", "EDN Confidential", rank=2
    )
    credential = BrowserInteractiveCredential(
        TENANT_ID, CLIENT_ID, ACCOUNT_ID, SCOPES
    )
    calendar_client = MicrosoftGraphCalendarClient(credential)
    outlook_client = MicrosoftGraphOutlookClient(credential)

    account = outlook_client.account()
    identities = {str(account.get("userPrincipalName", "")).casefold()}
    if account.get("mail") is not None:
        identities.add(str(account["mail"]).casefold())
    if ACCOUNT_ID.casefold() not in identities:
        raise PermissionError("authenticated Microsoft account does not match PA-005")
    folders = outlook_client.folders("me")
    if len(folders) != 1:
        raise PermissionError("PA-005 requires exactly one resolved Inbox")
    inbox_id = str(folders[0]["id"])

    calendar = MicrosoftCalendarConnector(
        CalendarConfig(
            TENANT_ID,
            ACCOUNT_ID,
            "default",
            "Default calendar",
            TIMEZONE,
            domain,
            classification,
            CalendarScopeMode.CATEGORY_REQUIRED,
            CATEGORY,
        ),
        calendar_client,
    )
    outlook = MicrosoftOutlookConnector(
        OutlookConfig(
            TENANT_ID,
            ACCOUNT_ID,
            "me",
            (inbox_id,),
            domain,
            classification,
            MailScopeMode.CATEGORY_REQUIRED,
            CATEGORY,
            authority_folder_ids=("inbox",),
        ),
        outlook_client,
    )
    now = datetime.now(UTC)
    calendar_result = calendar.search_events(
        _request(calendar, domain, classification, ("default", "window:this-week")),
        window=CalendarWindow.THIS_WEEK,
        now=now,
        limit=LIMIT,
    )
    mail_result = outlook.search_messages(
        _request(
            outlook, domain, classification, ("me", "inbox", "window:last-7-days")
        ),
        window=MailWindow.LAST_7_DAYS,
        now=now,
        limit=LIMIT,
    )
    return {
        "operation": "pa005-bounded-live-validation",
        "retrieved_at": now.isoformat(),
        "tenant_id": TENANT_ID,
        "account_id": ACCOUNT_ID,
        "delegated_permissions": list(SCOPES),
        "domain": domain.to_dict(),
        "classification": classification.to_dict(),
        "calendar": {
            "id": "default",
            "window": "this-week",
            "category": CATEGORY,
            "events": [item.to_dict() for item in calendar_result.events],
        },
        "mail": {
            "folder": "inbox",
            "folder_id": inbox_id,
            "window": "last-7-days",
            "category": CATEGORY,
            "messages": [_mail_dict(item) for item in mail_result.messages],
        },
        "counts": {
            "calendar_retrieved": calendar_result.pre_filter_count,
            "calendar_admitted": calendar_result.admitted_count,
            "mail_retrieved": mail_result.pre_filter_count,
            "mail_admitted": mail_result.admitted_count,
        },
        "body_reads": 0,
        "attachment_reads": 0,
        "source_mutations": 0,
    }


def _request(
    connector: Any,
    domain: SecurityDomain,
    classification: Classification,
    scope: tuple[str, ...],
) -> ConnectorRequest:
    capability_id = (
        "calendar.search"
        if connector.manifest.connector_id == "microsoft-calendar"
        else "outlook.search"
    )
    principal = PrincipalContext(
        "local-owner", CORE_TENANT_ID, frozenset({domain}), True
    )
    purpose = Purpose("pa005-live-validation", "Owner-approved PA-005 validation")
    permission = PermissionRequest(
        "pa005-policy", principal, purpose, capability_id, "search",
        domain, classification, scope,
    )
    manifest = next(
        item for item in connector.manifest.capabilities
        if item.capability_id == capability_id
    )
    registry = CapabilityRegistry()
    registry.register(
        manifest,
        CapabilityRuntimeState(
            CapabilityStatus.READY, AuthenticationStatus.VALID, health="live-approved"
        ),
    )
    evaluator = PermissionEvaluator(
        PolicySet(
            "pa005-exact-live-approval", "1",
            (PolicyRule(
                "pa005-exact-read", PermissionOutcome.ALLOWED_WITHIN_SCOPE,
                "Owner-approved bounded read-only validation.",
                principal_ids=frozenset({principal.principal_id}),
                domain_ids=frozenset({domain.domain_id}),
                purpose_ids=frozenset({purpose.purpose_id}),
                capability_ids=frozenset({capability_id}),
                operations=frozenset({"search"}),
                resource_scopes=frozenset(scope),
            ),),
        )
    )
    decision = evaluate_capability_use(
        registry, evaluator, permission, now=datetime.now(UTC)
    )
    return ConnectorRequest(
        f"pa005-{capability_id}", "pa005-live-correlation", principal, purpose,
        domain, classification, capability_id, "search", decision, scope,
    )


def _mail_dict(item: Any) -> dict[str, object]:
    return {
        "message_id": item.message_id,
        "folder_id": item.folder_id,
        "subject": item.subject,
        "sender": item.sender,
        "recipients": list(item.recipients),
        "received_at": item.received_at.isoformat(),
        "last_modified_at": item.last_modified_at.isoformat(),
        "importance": item.importance,
        "is_read": item.is_read,
        "categories": list(item.categories),
        "web_url": item.web_url,
    }


def _validate_output(output: Path) -> None:
    if output.exists() or not output.parent.is_dir():
        raise ValueError(
            "output parent must exist and output must be a no-clobber file"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "validate-live"))
    parser.add_argument("--output", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
