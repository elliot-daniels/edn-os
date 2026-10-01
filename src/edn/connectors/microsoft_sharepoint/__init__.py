"""Synthetic read-only Microsoft SharePoint connector."""

from edn.connectors.microsoft_sharepoint.client import GraphSharePointClient
from edn.connectors.microsoft_sharepoint.connector import (
    CONNECTOR_ID,
    CONNECTOR_VERSION,
    READ_PERMISSION,
    MicrosoftSharePointConnector,
)
from edn.connectors.microsoft_sharepoint.models import (
    SharePointConfig,
    SharePointRecord,
    SharePointRetrievalResult,
)

__all__ = [
    "CONNECTOR_ID",
    "CONNECTOR_VERSION",
    "READ_PERMISSION",
    "GraphSharePointClient",
    "MicrosoftSharePointConnector",
    "SharePointConfig",
    "SharePointRecord",
    "SharePointRetrievalResult",
]
