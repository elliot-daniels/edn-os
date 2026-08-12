"""Microsoft Graph request boundary; automated tests provide an in-memory fake."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, cast

import msal  # type: ignore[import-untyped]

ALLOWED_DELEGATED_SCOPES = frozenset({"Calendars.Read", "Mail.Read"})


class GraphCalendarClient(Protocol):
    def calendars(self) -> tuple[dict[str, Any], ...]: ...

    def calendar_view(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
        *,
        timezone_name: str,
        limit: int,
    ) -> tuple[dict[str, Any], ...]: ...


class TokenProvider(Protocol):
    def acquire_token(self) -> str: ...


class DeviceCodeCredential:
    """Interactive delegated token acquisition with no credential persistence."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        scopes: tuple[str, ...] = ("Calendars.Read",),
        *,
        prompt: Callable[[str], None] = print,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        if not scopes or len(scopes) != len(set(scopes)):
            raise ValueError("delegated scopes must be nonempty and unique")
        if not set(scopes) <= ALLOWED_DELEGATED_SCOPES:
            raise ValueError("delegated scope exceeds the PA-005 read-only boundary")
        self.scopes = scopes
        self._prompt = prompt
        self._opener = opener
        self._sleep = sleep
        self._token: str | None = None

    def acquire_token(self) -> str:
        if self._token is not None:
            return self._token
        endpoint = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0"
        device = self._post(
            f"{endpoint}/devicecode",
            {
                "client_id": self.client_id,
                "scope": " ".join(
                    f"https://graph.microsoft.com/{scope}" for scope in self.scopes
                ),
            },
        )
        self._prompt(str(device["message"]))
        interval = int(device.get("interval", 5))
        deadline = time.monotonic() + int(device["expires_in"])
        while time.monotonic() < deadline:
            self._sleep(interval)
            token = self._post(
                f"{endpoint}/token",
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id,
                    "device_code": str(device["device_code"]),
                },
                allow_pending=True,
            )
            if "access_token" in token:
                self._token = str(token["access_token"])
                return self._token
            if token.get("error") not in {"authorization_pending", "slow_down"}:
                raise RuntimeError("Microsoft delegated authentication failed safely.")
        raise RuntimeError("Microsoft delegated authentication expired.")

    def _post(
        self,
        url: str,
        fields: dict[str, str],
        *,
        allow_pending: bool = False,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=30) as response:
                return _json_object(response.read())
        except urllib.error.HTTPError as error:
            if allow_pending:
                return _json_object(error.read())
            raise RuntimeError(
                "Microsoft authentication endpoint was unavailable."
            ) from error


class BrowserInteractiveCredential:
    """System-browser auth-code/PKCE credential with memory-only token state."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        account_id: str,
        scopes: tuple[str, ...],
        *,
        app_factory: Callable[..., Any] = msal.PublicClientApplication,
        port: int = 8400,
    ) -> None:
        if not scopes or len(scopes) != len(set(scopes)):
            raise ValueError("delegated scopes must be nonempty and unique")
        if not set(scopes) <= ALLOWED_DELEGATED_SCOPES:
            raise ValueError("delegated scope exceeds the PA-005 read-only boundary")
        if not tenant_id.strip() or not client_id.strip() or not account_id.strip():
            raise ValueError("Microsoft identity values must be nonblank")
        if not 1024 <= port <= 65535:
            raise ValueError("interactive loopback port must be unprivileged")
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.account_id = account_id
        self.scopes = scopes
        self.port = port
        self._app_factory = app_factory
        self._token: str | None = None

    def acquire_token(self) -> str:
        if self._token is not None:
            return self._token
        app = self._app_factory(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=msal.TokenCache(),
        )
        result = app.acquire_token_interactive(
            scopes=[f"https://graph.microsoft.com/{scope}" for scope in self.scopes],
            login_hint=self.account_id,
            prompt="select_account",
            timeout=600,
            port=self.port,
        )
        if not isinstance(result, dict) or "access_token" not in result:
            raise RuntimeError("Microsoft browser authentication failed safely")
        claims = result.get("id_token_claims")
        if not isinstance(claims, dict):
            raise RuntimeError("Microsoft identity claims were unavailable")
        tenant = str(claims.get("tid", ""))
        account = str(
            claims.get("preferred_username") or claims.get("upn") or ""
        ).casefold()
        if tenant != self.tenant_id or account != self.account_id.casefold():
            raise PermissionError(
                "authenticated Microsoft identity does not match PA-005"
            )
        granted = {
            value.removeprefix("https://graph.microsoft.com/")
            for value in str(result.get("scope", "")).split()
            if value not in {"openid", "profile", "email", "offline_access"}
        }
        if granted != set(self.scopes):
            raise PermissionError("granted Microsoft permissions do not match PA-005")
        self._token = str(result["access_token"])
        return self._token


class MicrosoftGraphCalendarClient:
    """Small read-only Graph client; every requested field is explicit."""

    _BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self._token_provider = token_provider
        self._opener = opener
        self._token: str | None = None

    def calendars(self) -> tuple[dict[str, Any], ...]:
        return self._get_all(
            f"{self._BASE}/me/calendars?%24select=id,name,canEdit,owner,isDefaultCalendar"
        )

    def calendar_view(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
        *,
        timezone_name: str,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 25:
            raise ValueError("calendar live-read limit must be between 1 and 25")
        query = urllib.parse.urlencode(
            {
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$select": (
                    "id,subject,start,end,organizer,attendees,location,isAllDay,"
                    "recurrence,webLink,lastModifiedDateTime,categories"
                ),
                "$orderby": "start/dateTime",
                "$top": str(limit),
            }
        )
        path = "me/calendarView"
        if calendar_id != "default":
            identifier = urllib.parse.quote(calendar_id, safe="")
            path = f"me/calendars/{identifier}/calendarView"
        return self._get_all(
            f"{self._BASE}/{path}?{query}",
            timezone_name=timezone_name,
            max_items=limit,
        )

    def _get_all(
        self,
        url: str,
        *,
        timezone_name: str | None = None,
        max_items: int | None = None,
    ) -> tuple[dict[str, Any], ...]:
        values: list[dict[str, Any]] = []
        next_url: str | None = url
        pages = 0
        while next_url is not None:
            pages += 1
            if pages > 10:
                raise RuntimeError(
                    "Microsoft Graph pagination exceeded the safe bound."
                )
            payload = self._get(next_url, timezone_name=timezone_name)
            raw_values = payload.get("value")
            if not isinstance(raw_values, list):
                raise RuntimeError("Microsoft Graph returned an unexpected response.")
            values.extend(cast(dict[str, Any], item) for item in raw_values)
            if max_items is not None and len(values) >= max_items:
                return tuple(values[:max_items])
            candidate = payload.get("@odata.nextLink")
            next_url = None if candidate is None else str(candidate)
        return tuple(values)

    def _get(self, url: str, *, timezone_name: str | None = None) -> dict[str, Any]:
        if self._token is None:
            self._token = self._token_provider.acquire_token()
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if timezone_name is not None:
            headers["Prefer"] = f'outlook.timezone="{timezone_name}"'
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._opener(request, timeout=30) as response:
                return _json_object(response.read())
        except urllib.error.HTTPError as error:
            raise RuntimeError("Microsoft Graph read failed safely.") from error


def _json_object(value: bytes) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise RuntimeError("Microsoft endpoint returned an unexpected response.")
    return parsed
