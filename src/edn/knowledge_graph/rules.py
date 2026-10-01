"""Configurable deterministic entity extraction rules."""

from __future__ import annotations

import re
from dataclasses import dataclass

from edn.knowledge_graph.entities import EntityType

RULE_VERSION = "1"


@dataclass(frozen=True, slots=True)
class NamedPattern:
    """A canonical entity name and its case-insensitive matching expression."""

    entity_type: EntityType
    canonical_name: str
    expression: str


DEFAULT_NAMED_PATTERNS = (
    NamedPattern(
        EntityType.PROJECT, "Provisioning Requests", r"\bprovisioning requests?\b"
    ),
    NamedPattern(EntityType.PROJECT, "SAGRN", r"\bSAGRN\b"),
    NamedPattern(EntityType.PROJECT, "AP/PI", r"\bAP\s*/\s*PI\b"),
    NamedPattern(EntityType.CLIENT, "Services Australia", r"\bServices Australia\b"),
    NamedPattern(EntityType.CLIENT, "Defence", r"\bDefen[cs]e\b"),
    NamedPattern(EntityType.CLIENT, "NBN", r"\bNBN\b"),
    NamedPattern(EntityType.TECHNOLOGY, "Nokia PSS", r"\bNokia\s+PSS\b"),
    NamedPattern(EntityType.TECHNOLOGY, "Ciena", r"\bCiena\b"),
    NamedPattern(EntityType.TECHNOLOGY, "Cisco", r"\bCisco\b"),
    NamedPattern(EntityType.TECHNOLOGY, "ADVA", r"\bADVA\b"),
    NamedPattern(EntityType.TECHNOLOGY, "Juniper", r"\bJuniper\b"),
    NamedPattern(EntityType.TECHNOLOGY, "DWDM", r"\bDWDM\b"),
    NamedPattern(EntityType.EQUIPMENT, "MX304", r"\bMX304\b"),
    NamedPattern(EntityType.EQUIPMENT, "MTS5800", r"\bMTS[- ]?5800\b"),
    NamedPattern(EntityType.EQUIPMENT, "EXFO", r"\bEXFO\b"),
    NamedPattern(EntityType.EQUIPMENT, "OTDR", r"\bOTDR\b"),
    NamedPattern(EntityType.EQUIPMENT, "QSFP", r"\bQSFP(?:28)?\b"),
    NamedPattern(EntityType.SITE, "Pimba", r"\bPimba\b"),
    NamedPattern(EntityType.SITE, "Whyalla", r"\bWhyalla\b"),
    NamedPattern(EntityType.SITE, "Adelaide", r"\bAdelaide\b"),
    NamedPattern(EntityType.SITE, "Darwin", r"\bDarwin\b"),
    NamedPattern(EntityType.SKILL, "Commissioning", r"\bcommission(?:ed|ing)?\b"),
    NamedPattern(EntityType.SKILL, "Troubleshooting", r"\btroubleshoot(?:ing|ed)?\b"),
)

IDENTIFIER_PATTERNS = (
    (EntityType.PROJECT, re.compile(r"\bCRQ[- ]?\d{3,}\b", re.IGNORECASE)),
    (
        EntityType.INCIDENT,
        re.compile(r"\b(?:INC|CHG|TASK)[-_ ]?\d{4,}\b", re.IGNORECASE),
    ),
    (
        EntityType.IDENTIFIER,
        re.compile(
            r"\b(?=[A-Z0-9._-]*[A-Z])(?=[A-Z0-9._-]*\d)"
            r"[A-Z0-9]+(?:[._-][A-Z0-9]+){1,}\b",
            re.IGNORECASE,
        ),
    ),
)


def normalize_entity_name(value: str) -> str:
    """Return a stable identity key while preserving technical punctuation."""
    return " ".join(value.casefold().split())


def canonical_identifier(value: str) -> str:
    """Normalize separator whitespace and casing for structured identifiers."""
    return re.sub(r"\s+", "", value).upper()
