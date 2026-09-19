"""Explicit one-shot launch only; importing this module performs no I/O."""

from __future__ import annotations

import json
import os
import stat
import subprocess
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
EXECUTION_SID = "S-1-5-21-2158520141-276418557-3228345628-1003"
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
        or evidence.get("owner_sid") != EXECUTION_SID
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


def launch() -> Path:
    """Only invoke after separate owner approval of authentication AND inspection."""
    check_storage()
    app = msal.PublicClientApplication(
        APPLICATION,
        authority=f"https://login.microsoftonline.com/{TENANT}",
        token_cache=msal.TokenCache(),
        exclude_scopes=["offline_access"],
    )
    result = app.acquire_token_interactive(
        scopes=list(SCOPES),
        login_hint=ACCOUNT,
        prompt="select_account",
        timeout=600,
        port=8400,
    )
    token = validate_auth(result)
    # No result/token logging or serialization. No refresh or token supplier I/O.
    result.clear()
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
