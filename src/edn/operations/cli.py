"""Explicit local initialization and read-only Outlook import commands."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import msal  # type: ignore[import-untyped]

from edn.connectors.microsoft_calendar.client import DeviceCodeCredential
from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.outlook import (
    OperationsOutlookClient,
    ingest_mailbox,
    validate_window,
)
from edn.operations.storage import EventStore


class ApplicationCredential:
    """Reuse the website's Microsoft app configuration, without persisting tokens."""

    def __init__(self, tenant: str, client_id: str, secret: str) -> None:
        self.app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant}",
            client_credential=secret,
        )

    def acquire_token(self) -> str:
        result = self.app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        token = result.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Microsoft application authentication failed safely")
        return token


def runtime_database(database: str, data_root: str) -> Path:
    path, root = Path(database), Path(data_root)
    if not path.is_absolute() or not root.is_absolute():
        raise ValueError("Operations database and data root must be absolute")
    path, root = path.resolve(), root.resolve()
    if not path.is_relative_to(root) or not path.parent.is_dir():
        raise ValueError("Database parent must exist beneath the approved data root")
    if any((parent / ".git").exists() for parent in (path.parent, *path.parents)):
        raise ValueError("Operational data must stay outside Git repositories")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "ingest-outlook", "import-status"))
    parser.add_argument("--database", default=os.environ.get("EDN_OPERATIONS_DB"))
    parser.add_argument(
        "--data-root", default=os.environ.get("EDN_DATA_ROOT", r"E:\EDN OS")
    )
    parser.add_argument("--start", help="Inclusive ISO timestamp with timezone")
    parser.add_argument("--end", help="Inclusive ISO timestamp with timezone")
    parser.add_argument(
        "--auth", choices=("delegated", "application"), default="delegated"
    )
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args(argv)
    if not args.database:
        parser.error("Set EDN_OPERATIONS_DB or --database")
    try:
        path = runtime_database(args.database, args.data_root)
        store = EventStore(path)
        outcomes = ImportOutcomeStore(path)
        if args.command == "init":
            if path.is_file():
                outcomes.validate()
            store.initialise()
            outcomes.initialise()
            print(json.dumps({"initialized": True}))
            return 0
        if not path.is_file():
            raise ValueError("Initialize the Operations database before ingestion")
        if args.command == "import-status":
            history = ImportOutcomeStore(path, read_only=True).latest()
            print(
                json.dumps(
                    {
                        "coverage": "requested_inbox_windows_only",
                        "runs": [asdict(run) for run in history],
                    }
                )
            )
            return 0
        if not args.start or not args.end:
            raise ValueError("Outlook import requires --start and --end")
        start, end = (
            datetime.fromisoformat(args.start),
            datetime.fromisoformat(args.end),
        )
        validate_window(start, end)
        outcomes.initialise()
        if not 1 <= args.max_pages <= 100:
            raise ValueError("Page limit must be between 1 and 100")
        mailboxes = tuple(
            value.strip().casefold()
            for value in os.environ.get("EDN_OPERATIONS_MAILBOXES", "").split(",")
            if value.strip()
        )
        tenant, client_id = (
            os.environ["EDN_MS_TENANT_ID"],
            os.environ["EDN_MS_CLIENT_ID"],
        )
        if args.auth == "application":
            credential = ApplicationCredential(
                tenant, client_id, os.environ["EDN_MS_CLIENT_SECRET"]
            )
            client = OperationsOutlookClient(credential, mailboxes=mailboxes)
        else:
            delegated = DeviceCodeCredential(
                tenant, client_id, scopes=("User.Read", "Mail.Read")
            )
            client = OperationsOutlookClient(delegated, mailboxes=mailboxes)
            account = client.account()
            identities = {
                str(account.get(key, "")).casefold()
                for key in ("mail", "userPrincipalName")
            }
            if len(mailboxes) != 1 or mailboxes[0] not in identities:
                raise ValueError(
                    "Delegated Mail.Read requires the signed-in business mailbox"
                )
        complete = True
        for mailbox in mailboxes:
            try:
                report = ingest_mailbox(
                    client,
                    store,
                    mailbox,
                    start,
                    end,
                    max_pages=args.max_pages,
                    outcomes=outcomes,
                )
            except Exception:
                # Never print source/network exception strings or raw payloads.
                print(
                    json.dumps(
                        {
                            "mailbox": mailbox,
                            "complete": False,
                            "reason": "import_error",
                            "recent_outcomes": [
                                asdict(run)
                                for run in outcomes.latest(account=mailbox, limit=20)
                            ],
                        }
                    )
                )
                complete = False
                continue
            print(json.dumps({"mailbox": mailbox, **asdict(report)}))
            complete = complete and report.complete
        return 0 if complete else 1
    except (ValueError, KeyError) as error:
        parser.error(
            str(error)
            if isinstance(error, ValueError)
            else "Microsoft configuration is incomplete"
        )


if __name__ == "__main__":
    raise SystemExit(main())
