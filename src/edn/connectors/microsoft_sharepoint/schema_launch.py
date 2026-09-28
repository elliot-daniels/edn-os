"""Explicit one-shot launch only; importing this module performs no I/O."""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import subprocess
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import msal  # type: ignore[import-untyped]

from edn.connectors.microsoft_sharepoint.schema_executor import (
    ACCOUNT,
    APPLICATION,
    TENANT,
    SchemaExecutor,
    SchemaHttpTransport,
    SchemaIdentity,
    SchemaInspectionError,
    SchemaMode,
    require_mode,
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


def validate_acl(evidence: dict[str, Any], *, child: bool = False) -> None:
    expected = {
        "S-1-5-18": 2032127,
        "S-1-5-32-544": 2032127,
        str(evidence.get("admin_sid")): 2032127,
        EXECUTION_SID: 1245631,  # Modify plus Windows Synchronize
    }
    if (
        evidence.get("execution_sid") != EXECUTION_SID
        or evidence.get("owner_sid") != (EXECUTION_SID if child else PREPARATION_SID)
        or evidence.get("protected") is not (not child)
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
            or rule.get("inherited") is not child
            or rule.get("inheritance") != 3
            or rule.get("propagation") != 0
        ):
            raise SchemaInspectionError("storage_acl")
        seen.add(sid)


def check_path(path: Path) -> None:
    if not path.is_dir():
        raise SchemaInspectionError("storage_platform_or_missing")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (
            getattr(ancestor.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise SchemaInspectionError("storage_reparse")
        if (ancestor / ".git").exists():
            raise SchemaInspectionError("storage_inside_git")
    for name, value in os.environ.items():
        if (
            name.lower().startswith(("onedrive", "dropbox", "googledrive"))
            and value
            and path.resolve(strict=True).is_relative_to(Path(value).resolve())
        ):
            raise SchemaInspectionError("storage_cloud_sync")


def check_run_path(path: Path) -> None:
    if not re.fullmatch(r"run-[0-9a-f]{32}", path.name):
        raise SchemaInspectionError("storage_run_id")
    check_path(OUTPUT)
    check_path(path)
    root = OUTPUT.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if path.parent != OUTPUT or resolved.parent != root or resolved == root:
        raise SchemaInspectionError("storage_containment")
    if any(path.iterdir()):
        raise SchemaInspectionError("storage_not_empty_or_prior_attempt")


def check_storage(run_directory: Path | None = None) -> None:
    if os.name != "nt":
        raise SchemaInspectionError("storage_platform_or_missing")
    check_path(OUTPUT)
    validate_acl(inspect_acl(OUTPUT))
    if run_directory is not None:
        check_run_path(run_directory)
        validate_acl(inspect_acl(run_directory), child=True)


def inspect_acl(path: Path) -> dict[str, Any]:
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
    script = script.replace("$p=$args[0]", "$p='" + str(path).replace("'", "''") + "'")
    result = subprocess.run(
        ["pwsh.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise SchemaInspectionError("storage_acl_unavailable")
    try:
        evidence = json.loads(result.stdout)
        if not isinstance(evidence, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise SchemaInspectionError("storage_acl_unavailable") from None
    return evidence


def storage_probe(directory: Path) -> None:
    probe = directory / (".storage-test-" + uuid4().hex)
    created = False
    try:
        with probe.open("x", encoding="ascii") as handle:
            created = True
            handle.write("EDN harmless storage validation")
        if probe.read_text(encoding="ascii") != "EDN harmless storage validation":
            raise OSError
    except OSError:
        raise SchemaInspectionError("storage_probe_failed") from None
    finally:
        if created:
            try:
                probe.unlink()
                if probe.exists():
                    raise OSError
            except OSError:
                raise SchemaInspectionError("storage_probe_cleanup_failed") from None


def prepare_run() -> Path:
    check_storage()
    directory = OUTPUT / ("run-" + uuid4().hex)
    try:
        directory.mkdir(exist_ok=False)
    except OSError:
        raise SchemaInspectionError("storage_run_collision_or_denied") from None
    # Never reuse/delete a child, including one left empty by failed authentication.
    check_storage(directory)
    storage_probe(directory)
    check_storage(directory)
    return directory


AUTH_VALIDATION_REASONS = frozenset(
    {
        "authentication_result_invalid",
        "authentication_response_error",
        "authentication_consent_required",
        "authentication_claims_missing",
        "authentication_tenant_mismatch",
        "authentication_client_id_mismatch",
        "authentication_account_mismatch",
        "authentication_required_scope_missing",
        "authentication_unexpected_scope",
        "authentication_scope_format",
        "authentication_token_invalid",
    }
)


# Applies only after validate_auth verifies this exact tenant and application.
REQUIRED_OPERATION_SCOPES = frozenset({"Sites.Selected"})
ALLOWED_APPLICATION_SCOPES = frozenset(
    {"Sites.Selected", "User.Read", "Mail.Read", "Calendars.Read"}
)


SAFE_SCOPE_NAMES = frozenset(
    {
        "Sites.Selected",
        "User.Read",
        "Mail.Read",
        "Calendars.Read",
        "Sites.Read.All",
        "Sites.FullControl.All",
    }
)


def report_unexpected_scopes(scopes: set[str]) -> None:
    # Emit only exact, reviewed constants, never arbitrary token-response text.
    # Casing remains significant, just as in the unchanged exact-scope guard.
    unexpected = scopes - ALLOWED_APPLICATION_SCOPES
    progress(
        "scope_diagnostic="
        + json.dumps(
            {
                "expected": sorted(REQUIRED_OPERATION_SCOPES),
                "allowed": sorted(ALLOWED_APPLICATION_SCOPES),
                "unexpected": sorted(unexpected & SAFE_SCOPE_NAMES),
                "unrecognized_redacted": bool(unexpected - SAFE_SCOPE_NAMES),
            },
            sort_keys=True,
        )
    )


def validate_auth(result: Any) -> str:
    if not isinstance(result, dict):
        raise SchemaInspectionError("authentication_result_invalid")
    if "error" in result:
        # Never echo provider error descriptions or infer consent from missing claims.
        reason = (
            "authentication_consent_required"
            if result.get("error") == "consent_required"
            else "authentication_response_error"
        )
        raise SchemaInspectionError(reason)
    claims = result.get("id_token_claims")
    if not isinstance(claims, dict) or any(
        not isinstance(claims.get(key), str) or not claims[key]
        for key in ("tid", "aud", "preferred_username")
    ):
        raise SchemaInspectionError("authentication_claims_missing")
    if claims["tid"] != TENANT:
        raise SchemaInspectionError("authentication_tenant_mismatch")
    if claims["aud"] != APPLICATION:
        raise SchemaInspectionError("authentication_client_id_mismatch")
    if claims["preferred_username"].casefold() != ACCOUNT:
        raise SchemaInspectionError("authentication_account_mismatch")
    scope_text = result.get("scope", "")
    if not isinstance(scope_text, str):
        raise SchemaInspectionError("authentication_scope_format")
    scopes = {
        scope.removeprefix("https://graph.microsoft.com/")
        for scope in scope_text.split()
        if scope not in {"openid", "profile", "email", "offline_access"}
    }
    if "Sites.Selected" not in scopes:
        raise SchemaInspectionError("authentication_required_scope_missing")
    if not scopes <= ALLOWED_APPLICATION_SCOPES:
        report_unexpected_scopes(scopes)
        raise SchemaInspectionError("authentication_unexpected_scope")
    token = result.get("access_token")
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise SchemaInspectionError("authentication_token_invalid")
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
            try:
                token = validate_auth(result)
            finally:
                if isinstance(result, dict):
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
            reason = "authentication_delivery_failed"
            if (
                stage == "identity and scopes"
                and isinstance(exc, SchemaInspectionError)
                and len(exc.args) == 1
                and isinstance(exc.args[0], str)
                and exc.args[0] in AUTH_VALIDATION_REASONS
            ):
                reason = exc.args[0]
            progress("failed at " + stage + "; reason=" + reason + "; no inspection")
            raise SchemaInspectionError("authentication_delivery_failed") from None


def launch(mode: SchemaMode = SchemaMode.FULL) -> Path:
    """Only invoke after separate owner approval of authentication AND inspection."""
    mode = require_mode(mode)
    directory = prepare_run()
    token = authenticate()
    check_storage(directory)
    identity = SchemaIdentity(
        TENANT, APPLICATION, ACCOUNT, frozenset({"Sites.Selected"}), GRANT_ID
    )
    return SchemaExecutor(identity, SchemaHttpTransport(lambda: token, mode), mode).run(
        directory
    )


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--approved-authenticate-and-inspect", action="store_true")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in SchemaMode],
        default=SchemaMode.FULL.value,
    )
    if sum(arg == "--mode" or arg.startswith("--mode=") for arg in sys.argv[1:]) > 1:
        parser.error("execution mode must be specified at most once")
    args = parser.parse_args()
    if not args.approved_authenticate_and_inspect:
        parser.error("separate owner approval required; no authentication started")
    try:
        path = launch(SchemaMode(args.mode))
    except Exception:
        raise SystemExit(
            "Schema launch stopped safely; do not retry automatically"
        ) from None
    print(f"Inspection finished: {path}")


if __name__ == "__main__":
    main()
