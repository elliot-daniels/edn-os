"""Synthetic-only read-only Microsoft Outlook connector."""

from edn.connectors.microsoft_outlook.client import GraphOutlookClient
from edn.connectors.microsoft_outlook.connector import MicrosoftOutlookConnector
from edn.connectors.microsoft_outlook.models import (
    MailScopeMode,
    MailWindow,
    OutlookConfig,
    OutlookMessage,
    OutlookRetrievalResult,
)

__all__ = [
    "GraphOutlookClient",
    "MailScopeMode",
    "MailWindow",
    "MicrosoftOutlookConnector",
    "OutlookConfig",
    "OutlookMessage",
    "OutlookRetrievalResult",
]
