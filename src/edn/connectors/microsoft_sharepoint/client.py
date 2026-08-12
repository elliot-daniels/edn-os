"""Synthetic client boundary for read-only SharePoint Business OS retrieval."""

from __future__ import annotations

from typing import Any, Protocol


class GraphSharePointClient(Protocol):
    def search_items(
        self,
        site_id: str,
        list_id: str,
        query: str,
        field_names: tuple[str, ...],
        *,
        limit: int,
    ) -> tuple[dict[str, Any], ...]: ...

    def list_fields(self, site_id: str, list_id: str) -> tuple[str, ...]: ...


# PA-006 deliberately has no HTTP, authentication, schema, or mutation client.
