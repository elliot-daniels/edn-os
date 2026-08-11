"""Synthetic-client boundary for future read-only Microsoft Graph mail access."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol


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


# PA-003 deliberately provides no HTTP/authentication implementation. Live Graph
# access remains a separately approved PA-005 capability boundary.
