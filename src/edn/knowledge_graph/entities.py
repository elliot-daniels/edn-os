"""Models for extracted entities, relationships, and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EntityType(StrEnum):
    """Supported deterministic knowledge categories."""

    PROJECT = "project"
    CLIENT = "client"
    PERSON = "person"
    SITE = "site"
    TECHNOLOGY = "technology"
    EQUIPMENT = "equipment"
    INCIDENT = "incident"
    SKILL = "skill"
    IDENTIFIER = "identifier"


@dataclass(frozen=True, slots=True)
class EntityMention:
    """One entity occurrence extracted from an email field."""

    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    field_name: str
    matched_text: str


@dataclass(frozen=True, slots=True)
class RelationshipFact:
    """A typed relationship supported by the current source email."""

    subject_type: EntityType
    subject_name: str
    predicate: str
    object_type: EntityType
    object_name: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """All deterministic knowledge derived from one email."""

    source_record_key: str
    mentions: tuple[EntityMention, ...]
    relationships: tuple[RelationshipFact, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeEntity:
    """A normalized entity with aggregate evidence counts."""

    entity_id: int
    entity_type: EntityType
    canonical_name: str
    normalized_name: str
    occurrence_count: int
    source_count: int

    @property
    def summary(self) -> str:
        return (
            f"{self.canonical_name} is supported by "
            f"{self.source_count} email{'s' if self.source_count != 1 else ''}."
        )


@dataclass(frozen=True, slots=True)
class RelatedEntity:
    """One relationship adjacent to a selected entity."""

    predicate: str
    entity: KnowledgeEntity
    direction: str
    source_count: int


@dataclass(frozen=True, slots=True)
class EntityDetails:
    """An entity, its graph neighbours, and supporting source keys."""

    entity: KnowledgeEntity
    related_entities: tuple[RelatedEntity, ...]
    source_record_keys: tuple[str, ...]
