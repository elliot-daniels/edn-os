"""Synthetic-client boundary for future read-only Microsoft Graph mail access."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, cast

from edn.connectors.errors import SourceUnavailableError


class TokenProvider(Protocol):
    def acquire_token(self) -> str: ...


class GraphOutlookClient(Protocol):
    def messages(
        self,
        mailbox_id: str,
        folder_id: str,
        start: datetime,
        end: datetime,
        *,
        limit: int,
    ) -> tuple[dict[str, Any], ...]: ...

    def folders(self, mailbox_id: str) -> tuple[dict[str, Any], ...]: ...

    def account(self) -> dict[str, Any]: ...


MAX_RESPONSE_BYTES = 1_048_576


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise urllib.error.URLError("Graph redirects are not permitted")


def _open_without_redirects(request: urllib.request.Request, **kwargs: Any) -> Any:
    return urllib.request.build_opener(_NoRedirectHandler()).open(request, **kwargs)


class MicrosoftGraphOutlookClient:
    """GET-only bounded Graph client with an explicit metadata projection."""

    _BASE = "https://graph.microsoft.com/v1.0"
    _MESSAGE_SELECT = (
        "id,parentFolderId,subject,from,toRecipients,receivedDateTime,"
        "lastModifiedDateTime,importance,isRead,categories,webLink"
    )

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        opener: Callable[..., Any] | None = None,
        prefer: str | None = None,
    ) -> None:
        self._token_provider = token_provider
        self._opener = opener or _open_without_redirects
        self._prefer = prefer
        self._token: str | None = None
        self._inbox_id: str | None = None

    def account(self) -> dict[str, Any]:
        return self._get(f"{self._BASE}/me?%24select=id,userPrincipalName,mail")

    def folders(self, mailbox_id: str) -> tuple[dict[str, Any], ...]:
        self._require_me(mailbox_id)
        folders = self._values(
            f"{self._BASE}/me/mailFolders/inbox?%24select=id,displayName"
        )
        if len(folders) != 1 or not isinstance(folders[0].get("id"), str):
            raise RuntimeError("Microsoft Graph did not resolve one Inbox folder")
        self._inbox_id = str(folders[0]["id"])
        return folders

    def messages(
        self,
        mailbox_id: str,
        folder_id: str,
        start: datetime,
        end: datetime,
        *,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        self._require_me(mailbox_id)
        if self._inbox_id is None or folder_id != self._inbox_id:
            raise ValueError("Inbox must be resolved and matched before message access")
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError("Outlook window must be bounded and timezone-aware")
        if not 1 <= limit <= 25:
            raise ValueError("Outlook live-read limit must be between 1 and 25")
        query = urllib.parse.urlencode(
            {
                "$select": self._MESSAGE_SELECT,
                "$filter": (
                    f"receivedDateTime ge {start.isoformat()} and "
                    f"receivedDateTime le {end.isoformat()}"
                ),
                "$orderby": "receivedDateTime desc",
                "$top": str(limit),
            }
        )
        identifier = urllib.parse.quote(folder_id, safe="")
        return self._values(
            f"{self._BASE}/me/mailFolders/{identifier}/messages?{query}", limit=limit
        )

    def _require_me(self, mailbox_id: str) -> None:
        if mailbox_id != "me":
            raise ValueError("PA-005 Outlook client accepts only /me mailbox")

    def _values(self, url: str, *, limit: int = 1) -> tuple[dict[str, Any], ...]:
        payload = self._get(url)
        if "value" not in payload:
            return (payload,)
        raw = payload["value"]
        if not isinstance(raw, list):
            raise RuntimeError("Microsoft Graph returned an unexpected response")
        # A continuation link can be present when more Inbox messages exist. The
        # PA-005 boundary deliberately ignores it and never performs a second GET.
        return tuple(cast(dict[str, Any], item) for item in raw[:limit])

    def _get(self, url: str) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme, parsed.netloc) != ("https", "graph.microsoft.com"):
            raise ValueError("Outlook reads require the exact Graph HTTPS origin")
        if self._token is None:
            self._token = self._token_provider.acquire_token()
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                **({"Prefer": self._prefer} if self._prefer else {}),
            },
            method="GET",
        )
        # Default transport rejects redirects. Unredirected credentials also
        # prevent credential copying by urllib if an alternate opener is injected.
        request.add_unredirected_header("Authorization", f"Bearer {self._token}")
        try:
            with self._opener(request, timeout=30) as response:
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceUnavailableError("Graph response exceeds byte limit")
                value = json.loads(content)
        except (urllib.error.URLError, TimeoutError) as error:
            raise SourceUnavailableError(
                "Microsoft Graph Outlook read failed safely"
            ) from error
        if not isinstance(value, dict):
            raise RuntimeError("Microsoft Graph returned an unexpected response")
        return value


# Legacy methods remain metadata-only; Operations supplies its own content projection.
