"""Local deterministic extraction of entities and relationships from emails."""

from __future__ import annotations

import re
from email.utils import parseaddr

from edn.knowledge_graph.entities import (
    EntityMention,
    EntityType,
    ExtractionResult,
    RelationshipFact,
)
from edn.knowledge_graph.rules import (
    DEFAULT_NAMED_PATTERNS,
    IDENTIFIER_PATTERNS,
    NamedPattern,
    canonical_identifier,
    normalize_entity_name,
)
from edn.memory.models import EmailRecord


class KnowledgeExtractor:
    """Apply a configurable rule set to one canonical email at a time."""

    def __init__(
        self,
        named_patterns: tuple[NamedPattern, ...] = DEFAULT_NAMED_PATTERNS,
    ) -> None:
        self._named_patterns = tuple(
            (rule, re.compile(rule.expression, re.IGNORECASE))
            for rule in named_patterns
        )

    def extract(self, record: EmailRecord) -> ExtractionResult:
        """Extract deduplicated mentions and co-occurrence relationships."""
        mentions: list[EntityMention] = []
        for field_name, text in (
            ("subject", record.subject),
            ("body", record.body_text),
        ):
            mentions.extend(self._extract_text(field_name, text))
        person = self._sender_mention(record.sender)
        if person is not None:
            mentions.append(person)
        unique_mentions = self._deduplicate_mentions(mentions)
        relationships = self._relationships(unique_mentions, record)
        return ExtractionResult(
            source_record_key=record.source_record_key,
            mentions=unique_mentions,
            relationships=relationships,
        )

    def _extract_text(self, field_name: str, text: str) -> list[EntityMention]:
        mentions: list[EntityMention] = []
        for rule, expression in self._named_patterns:
            for match in expression.finditer(text):
                mentions.append(
                    EntityMention(
                        entity_type=rule.entity_type,
                        canonical_name=rule.canonical_name,
                        normalized_name=normalize_entity_name(rule.canonical_name),
                        field_name=field_name,
                        matched_text=match.group(0),
                    )
                )
        for entity_type, expression in IDENTIFIER_PATTERNS:
            for match in expression.finditer(text):
                canonical = canonical_identifier(match.group(0))
                mentions.append(
                    EntityMention(
                        entity_type=entity_type,
                        canonical_name=canonical,
                        normalized_name=normalize_entity_name(canonical),
                        field_name=field_name,
                        matched_text=match.group(0),
                    )
                )
        return mentions

    @staticmethod
    def _sender_mention(sender: str) -> EntityMention | None:
        display_name, address = parseaddr(sender)
        canonical = display_name.strip().strip('"') or address.strip() or sender.strip()
        if not canonical or "@" not in (address or canonical):
            return None
        return EntityMention(
            entity_type=EntityType.PERSON,
            canonical_name=canonical,
            normalized_name=normalize_entity_name(address or canonical),
            field_name="sender",
            matched_text=sender,
        )

    @staticmethod
    def _deduplicate_mentions(
        mentions: list[EntityMention],
    ) -> tuple[EntityMention, ...]:
        unique: dict[tuple[EntityType, str, str], EntityMention] = {}
        for mention in mentions:
            key = (
                mention.entity_type,
                mention.normalized_name,
                mention.field_name,
            )
            unique.setdefault(key, mention)
        return tuple(unique.values())

    @staticmethod
    def _relationships(
        mentions: tuple[EntityMention, ...],
        record: EmailRecord,
    ) -> tuple[RelationshipFact, ...]:
        by_type: dict[EntityType, dict[str, EntityMention]] = {}
        for mention in mentions:
            by_type.setdefault(mention.entity_type, {})[mention.normalized_name] = (
                mention
            )

        facts: set[RelationshipFact] = set()

        def relate(
            left_type: EntityType,
            predicate: str,
            right_type: EntityType,
        ) -> None:
            for left in by_type.get(left_type, {}).values():
                for right in by_type.get(right_type, {}).values():
                    facts.add(
                        RelationshipFact(
                            left_type,
                            left.normalized_name,
                            predicate,
                            right_type,
                            right.normalized_name,
                        )
                    )

        relate(EntityType.PERSON, "works_on", EntityType.PROJECT)
        relate(EntityType.PROJECT, "uses", EntityType.TECHNOLOGY)
        relate(EntityType.PROJECT, "uses", EntityType.EQUIPMENT)
        relate(EntityType.CLIENT, "associated_with", EntityType.PROJECT)
        relate(EntityType.INCIDENT, "affects", EntityType.SITE)
        if re.search(r"\bcommission(?:ed|ing)?\b", record.body_text, re.IGNORECASE):
            relate(EntityType.TECHNOLOGY, "commissioned_at", EntityType.SITE)
            relate(EntityType.EQUIPMENT, "commissioned_at", EntityType.SITE)
        return tuple(
            sorted(
                facts,
                key=lambda fact: (
                    fact.subject_type,
                    fact.subject_name,
                    fact.predicate,
                    fact.object_type,
                    fact.object_name,
                ),
            )
        )
