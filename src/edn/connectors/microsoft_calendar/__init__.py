"""Read-only Microsoft 365 calendar connector."""

from edn.connectors.microsoft_calendar.client import (
    BrowserInteractiveCredential,
    DeviceCodeCredential,
    GraphCalendarClient,
    MicrosoftGraphCalendarClient,
)
from edn.connectors.microsoft_calendar.connector import MicrosoftCalendarConnector
from edn.connectors.microsoft_calendar.models import (
    CalendarAttendee,
    CalendarConfig,
    CalendarEvent,
    CalendarRetrievalResult,
    CalendarScopeMode,
    CalendarWindow,
)

__all__ = [
    "BrowserInteractiveCredential",
    "CalendarAttendee",
    "CalendarConfig",
    "CalendarEvent",
    "CalendarRetrievalResult",
    "CalendarScopeMode",
    "CalendarWindow",
    "DeviceCodeCredential",
    "GraphCalendarClient",
    "MicrosoftCalendarConnector",
    "MicrosoftGraphCalendarClient",
]
