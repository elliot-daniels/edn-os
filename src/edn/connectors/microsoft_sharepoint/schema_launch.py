"""Explicit one-shot launch only; importing this module performs no I/O."""

from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import msal  # type: ignore[import-untyped]

from edn.connectors.microsoft_sharepoint.schema_executor import (
    ACCOUNT,
    APPLICATION,
    TENANT,
    SchemaExecutor,
    SchemaHttpTransport,
    SchemaIdentity,
    SchemaInspectionError,
)

OUTPUT = Path(
    r"C:\Users\Admin\Documents\Codex\2026-09-14\files-pasted-by-the-user-edn\pilot-private\schema-8e4599f-one-shot"
)
PREPARATION_SID = "S-1-5-21-2158520141-276418557-3228345628-1003"
EXECUTION_SID = "S-1-5-21-2158520141-276418557-3228345628-1004"
GRANT_ID = (
    "aTowaS50fG1zLnNwLmV4dHwyMzgxZTRmNi00NGJjLTQ2OTctYWQ2NC1lODY1MTNj"
    "YjlkZWVAYWFlNmFiNzktNDVlYi00ODI5LWEwNGYtNTk1YmVjZGI5MzZk"
)
SCOPES = ("https://graph.microsoft.com/Sites.Selected",)


def validate_acl(evidence: dict[str, Any]) -> None:
    expected = {
        "S-1-5-18": 2032127,
        "S-1-5-32-544": 2032127,
        str(evidence.get("admin_sid")): 2032127,
        EXECUTION_SID: 1245631,  # Modify plus Windows Synchronize
    }
    if (
        evidence.get("execution_sid") != EXECUTION_SID
        or evidence.get("owner_sid") != PREPARATION_SID
        or evidence.get("protected") is not True
        or not str(evidence.get("admin_sid", "")).startswith(
            "S-1-5-21-2158520141-276418557-3228345628-"
        )
        or len(expected) != 4
    ):
        raise SchemaInspectionError("storage_identity_or_owner")
    rules = evidence.get("rules")
    if not isinstance(rules, list) or len(rules) != 4:
        raise SchemaInspectionError("storage_acl")
    seen = set()
    for rule in rules:
        sid = rule.get("sid")
        if (
            sid in seen
            or sid not in expected
            or rule.get("rights") != expected[sid]
            or rule.get("type") != "Allow"
            or rule.get("inherited") is not False
            or rule.get("inheritance") != 3
            or rule.get("propagation") != 0
        ):
            raise SchemaInspectionError("storage_acl")
        seen.add(sid)


def check_storage() -> None:
    if os.name != "nt" or not OUTPUT.is_dir():
        raise SchemaInspectionError("storage_platform_or_missing")
    for path in (OUTPUT, *OUTPUT.parents):
        if (
            path.is_symlink()
            or getattr(path.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise SchemaInspectionError("storage_reparse")
        if (path / ".git").exists():
            raise SchemaInspectionError("storage_inside_git")
    for name, value in os.environ.items():
        if (
            name.lower().startswith(("onedrive", "dropbox", "googledrive"))
            and value
            and OUTPUT.is_relative_to(Path(value))
        ):
            raise SchemaInspectionError("storage_cloud_sync")
    if any(OUTPUT.iterdir()):
        raise SchemaInspectionError("storage_not_empty_or_prior_attempt")
    # Read-only security-descriptor inspection, with no authentication or secrets.
    script = r"""
$ErrorActionPreference='Stop'
$p=$args[0]
$a=Get-Acl -LiteralPath $p -ErrorAction Stop
$admin=([Security.Principal.NTAccount]::new('ELLIOTS-PC','Admin')).Translate([Security.Principal.SecurityIdentifier]).Value
$owner=([Security.Principal.NTAccount]::new($a.Owner)).Translate([Security.Principal.SecurityIdentifier]).Value
$rules=@($a.Access | ForEach-Object {
$sid=$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
@{sid=$sid;
rights=[int]$_.FileSystemRights;
type=$_.AccessControlType.ToString();
inherited=$_.IsInherited;
inheritance=[int]$_.InheritanceFlags;
propagation=[int]$_.PropagationFlags} })
@{execution_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
admin_sid=$admin;
owner_sid=$owner;
protected=$a.AreAccessRulesProtected;
rules=$rules} | ConvertTo-Json -Depth 4 -Compress
"""
    # A literal fixed path, never caller-controlled PowerShell input.
    script = script.replace("$p=$args[0]", "$p='" + str(OUTPUT) + "'")
    result = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise SchemaInspectionError("storage_acl_unavailable")
    validate_acl(json.loads(result.stdout))


def validate_auth(result: Any) -> str:
    if not isinstance(result, dict):
        raise SchemaInspectionError("authentication_failed")
    claims = result.get("id_token_claims")
    if not isinstance(claims, dict) or (
        claims.get("tid") != TENANT
        or claims.get("aud") != APPLICATION
        or str(claims.get("preferred_username", "")).casefold() != ACCOUNT
    ):
        raise SchemaInspectionError("authentication_identity")
    scopes = {
        scope.removeprefix("https://graph.microsoft.com/")
        for scope in str(result.get("scope", "")).split()
        if scope not in {"openid", "profile", "email", "offline_access"}
    }
    token = result.get("access_token")
    if scopes != {"Sites.Selected"}:
        raise SchemaInspectionError("authentication_scopes")
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise SchemaInspectionError("authentication_token")
    return token


AUTH_NETWORK_TIMEOUT = 20
AUTH_INTERACTIVE_TIMEOUT = 600
LANDING_URL = "http://localhost:8400?welcome=true"


def progress(message: str) -> None:
    print("AUTH: " + message, flush=True)


@contextmanager
def browser_delivery() -> Iterator[dict[str, bool]]:
    """Process-scoped hook for this single-threaded CLI, restored on every exit."""
    original = webbrowser.open
    previous_logging = logging.root.manager.disable
    status = {"failed": False}

    def deliver(url: str, new: int = 0, autoraise: bool = True) -> bool:
        progress("browser handoff starting")
        try:
            accepted = url == LANDING_URL and original(url, new, autoraise)
        except Exception:
            accepted = False
        status["failed"] = not accepted
        progress("browser handoff accepted" if accepted else "browser handoff failed")
        if accepted:
            progress(
                "handoff is not proof of visibility; open "
                + LANDING_URL
                + " manually if needed"
            )
            progress("waiting for browser completion")
        return accepted

    # MSAL can log auth URIs and response details. Emit only our static milestones.
    logging.disable(logging.CRITICAL)
    webbrowser.open = deliver
    try:
        yield status
    finally:
        webbrowser.open = original
        logging.disable(previous_logging)


def authenticate() -> str:
    progress("preparing")
    stage = "authority discovery"
    with browser_delivery() as delivery:
        try:
            app = msal.PublicClientApplication(
                APPLICATION,
                authority=f"https://login.microsoftonline.com/{TENANT}",
                token_cache=msal.TokenCache(),
                exclude_scopes=["offline_access"],
                timeout=AUTH_NETWORK_TIMEOUT,
            )
            progress("authority ready")
            stage = "browser completion or token exchange"
            result = app.acquire_token_interactive(
                scopes=list(SCOPES),
                login_hint=ACCOUNT,
                prompt="select_account",
                timeout=AUTH_INTERACTIVE_TIMEOUT,
                port=8400,
                welcome_template=(
                    "<h1>EDN sign-in</h1>"
                    '<a href="$auth_uri">Continue to Microsoft sign-in</a>'
                    "<p>Use Elliot's account. Do not accept unexpected consent.</p>"
                ),
                success_template=(
                    "Authentication returned to EDN. Return to Codex "
                    "for identity/scope verification and inspection status. "
                    "You may close this tab."
                ),
                error_template="Authentication failed. Return to Codex; do not retry.",
                auth_uri_callback=lambda _uri: None,
            )
            if delivery["failed"]:
                raise SchemaInspectionError("browser_handoff_failed")
            progress("callback received")
            progress("validating identity and scopes")
            stage = "identity and scopes"
            token = validate_auth(result)
            result.clear()
            progress("success")
            return token
        except KeyboardInterrupt:
            progress("cancelled; no inspection")
            raise SchemaInspectionError("authentication_cancelled") from None
        except Exception as exc:
            from msal.oauth2cli.oauth2 import (  # type: ignore[import-untyped]
                BrowserInteractionTimeoutError,
            )

            if delivery["failed"]:
                stage = "browser handoff"
            elif isinstance(exc, BrowserInteractionTimeoutError):
                stage = "browser callback timeout"
            progress("failed at " + stage + "; no inspection")
            raise SchemaInspectionError("authentication_delivery_failed") from None


def launch() -> Path:
    """Only invoke after separate owner approval of authentication AND inspection."""
    check_storage()
    token = authenticate()
    check_storage()
    identity = SchemaIdentity(
        TENANT, APPLICATION, ACCOUNT, frozenset({"Sites.Selected"}), GRANT_ID
    )
    return SchemaExecutor(identity, SchemaHttpTransport(lambda: token)).run(OUTPUT)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-authenticate-and-inspect", action="store_true")
    args = parser.parse_args()
    if not args.approved_authenticate_and_inspect:
        parser.error("separate owner approval required; no authentication started")
    try:
        path = launch()
    except Exception:
        raise SystemExit(
            "Schema launch stopped safely; do not retry automatically"
        ) from None
    print(f"Inspection finished: {path}")


if __name__ == "__main__":
    main()
