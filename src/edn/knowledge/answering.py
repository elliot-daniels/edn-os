"""Grounded answer providers and citation validation."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from edn.knowledge.models import AnsweredQuestion, EmailEvidence, GroundedAnswer
from edn.retrieval.engine import DEFAULT_EVIDENCE_LIMIT, RetrievalEngine

PROVIDER_ENVIRONMENT_VARIABLE = "EDN_LLM_PROVIDER"
MAX_CONTEXT_CHARACTERS = 8_000
MAX_CONTEXT_EXCERPT_CHARACTERS = 1_200
MAX_EXTRACTIVE_SOURCES = 3
INSUFFICIENT_EVIDENCE_TEXT = (
    "I could not find sufficient email evidence to answer that question."
)


class AnswerProvider(Protocol):
    """Replaceable boundary for grounded answer generation."""

    def answer(
        self,
        question: str,
        evidence: Sequence[EmailEvidence],
    ) -> GroundedAnswer:
        """Generate an answer using only the supplied evidence."""


class AnswerConfigurationError(ValueError):
    """Raised when an answer provider is not safely configured."""


class AnswerGenerationError(RuntimeError):
    """Raised when an answer provider fails without exposing internals."""


class CitationValidationError(AnswerGenerationError):
    """Raised when an answer cites evidence it was not supplied."""


def build_bounded_context(
    evidence: Sequence[EmailEvidence],
    *,
    max_characters: int = MAX_CONTEXT_CHARACTERS,
) -> str:
    """Build bounded, numbered source context for a future model provider."""
    if max_characters < 100:
        raise ValueError("max_characters must be at least 100")

    blocks: list[str] = []
    used_characters = 0
    for item in evidence:
        excerpt = item.body_excerpt[:MAX_CONTEXT_EXCERPT_CHARACTERS]
        block = (
            f"SOURCE [{item.evidence_id}]\n"
            f"Subject: {item.subject}\n"
            f"Sender: {item.sender}\n"
            f"Date: {item.sent_at.isoformat() if item.sent_at else 'unknown'}\n"
            f"Folder: {item.folder_path}\n"
            f"Source key: {item.source_record_key}\n"
            f"Excerpt: {excerpt}\n"
        )
        separator_size = 1 if blocks else 0
        remaining = max_characters - used_characters - separator_size
        if remaining <= 0:
            break
        if len(block) > remaining:
            if not blocks:
                blocks.append(block[:remaining])
            break
        blocks.append(block)
        used_characters += len(block) + separator_size
    return "\n".join(blocks)


def build_grounded_instructions(question: str, context: str) -> str:
    """Create provider-neutral instructions without containing hidden credentials."""
    return (
        "Answer the question using only the numbered email sources below. "
        "Cite every substantive claim with source numbers such as [1]. "
        "Do not invent names, dates, decisions, causes, or outcomes. "
        "If the evidence is insufficient, say so explicitly.\n\n"
        f"QUESTION\n{question.strip()}\n\n"
        f"SOURCES\n{context}"
    )


class ExtractiveAnswerProvider:
    """Fully local provider that returns concise cited evidence extracts."""

    def answer(
        self,
        question: str,
        evidence: Sequence[EmailEvidence],
    ) -> GroundedAnswer:
        del question
        selected = tuple(evidence[:MAX_EXTRACTIVE_SOURCES])
        if not selected:
            return GroundedAnswer(
                text=INSUFFICIENT_EVIDENCE_TEXT,
                cited_evidence_ids=(),
                insufficient_evidence=True,
            )

        lines = ["Based only on the retrieved email evidence:"]
        for item in selected:
            excerpt = item.body_excerpt
            if len(excerpt) > 280:
                excerpt = excerpt[:279].rstrip() + "…"
            subject = item.subject or "(No subject)"
            lines.append(f"[{item.evidence_id}] {subject}: {excerpt}")
        return GroundedAnswer(
            text="\n\n".join(lines),
            cited_evidence_ids=tuple(item.evidence_id for item in selected),
        )


class DisabledAnswerProvider:
    """Provider used when answer generation is explicitly disabled."""

    def answer(
        self,
        question: str,
        evidence: Sequence[EmailEvidence],
    ) -> GroundedAnswer:
        del question, evidence
        return GroundedAnswer(
            text="Ask EDN answer generation is disabled by local configuration.",
            cited_evidence_ids=(),
            insufficient_evidence=True,
            warnings=("Set EDN_LLM_PROVIDER=extractive to enable local summaries.",),
        )


def resolve_answer_provider(
    environment: Mapping[str, str] | None = None,
) -> AnswerProvider:
    """Resolve an approved local provider without silently enabling cloud AI."""
    values = os.environ if environment is None else environment
    provider_name = values.get(PROVIDER_ENVIRONMENT_VARIABLE, "extractive")
    normalized_name = provider_name.strip().casefold()
    if normalized_name in {"", "extractive", "local"}:
        return ExtractiveAnswerProvider()
    if normalized_name in {"disabled", "off", "none"}:
        return DisabledAnswerProvider()
    raise AnswerConfigurationError(
        f"Unsupported {PROVIDER_ENVIRONMENT_VARIABLE} value. "
        "Use 'extractive' or 'disabled'."
    )


def validate_grounded_answer(
    answer: GroundedAnswer,
    evidence: Sequence[EmailEvidence],
) -> None:
    """Reject missing, duplicate, or fabricated source citations."""
    valid_ids = {item.evidence_id for item in evidence}
    cited_ids = answer.cited_evidence_ids
    if len(cited_ids) != len(set(cited_ids)):
        raise CitationValidationError("The answer returned duplicate citations.")
    if any(citation not in valid_ids for citation in cited_ids):
        raise CitationValidationError("The answer returned an invalid citation.")
    if not answer.insufficient_evidence and not cited_ids:
        raise CitationValidationError("The grounded answer did not cite a source.")
    text_citations = tuple(
        dict.fromkeys(int(value) for value in re.findall(r"\[(\d+)\]", answer.text))
    )
    if text_citations != cited_ids:
        raise CitationValidationError(
            "The answer text citations do not match its declared sources."
        )


def answer_question(
    question: str,
    retrieval_engine: RetrievalEngine,
    provider: AnswerProvider,
    *,
    retrieval_limit: int = DEFAULT_EVIDENCE_LIMIT,
) -> AnsweredQuestion:
    """Retrieve evidence, generate an answer, and validate all citations."""
    evidence = retrieval_engine.retrieve(question, limit=retrieval_limit)
    if not evidence:
        return AnsweredQuestion(
            answer=GroundedAnswer(
                text=INSUFFICIENT_EVIDENCE_TEXT,
                cited_evidence_ids=(),
                insufficient_evidence=True,
            ),
            evidence=(),
        )

    try:
        answer = provider.answer(question, evidence)
    except Exception as error:
        raise AnswerGenerationError(
            "Ask EDN could not generate an answer from the retrieved evidence."
        ) from error
    validate_grounded_answer(answer, evidence)
    return AnsweredQuestion(answer=answer, evidence=evidence)
