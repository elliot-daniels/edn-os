"""Tests for grounded answer generation and citation validation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edn.knowledge.answering import (
    AnswerConfigurationError,
    AnswerGenerationError,
    CitationValidationError,
    DisabledAnswerProvider,
    ExtractiveAnswerProvider,
    answer_question,
    build_bounded_context,
    build_grounded_instructions,
    resolve_answer_provider,
    validate_grounded_answer,
)
from edn.knowledge.models import EmailEvidence, GroundedAnswer
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import RetrievalEngine


def _evidence(
    evidence_id: int,
    *,
    excerpt: str = "Pimba was restored.",
) -> EmailEvidence:
    return EmailEvidence(
        evidence_id=evidence_id,
        source_record_key=f"source-{evidence_id}",
        subject=f"Incident update {evidence_id}",
        sender="engineer@example.com",
        sent_at=datetime(2026, 7, 18, 10, 30, tzinfo=UTC),
        folder_path="Inbox/Incidents",
        message_id=f"<message-{evidence_id}@example.com>",
        body_excerpt=excerpt,
        body_text=excerpt,
    )


def _store_with_pimba_email(tmp_path: Path) -> SQLiteEmailStore:
    store = SQLiteEmailStore(tmp_path / "memory.db")
    store.initialise()
    store.add(
        EmailRecord(
            source_record_key="pimba-email",
            folder_path="Inbox/Incidents",
            subject="Pimba restoration",
            sender="engineer@example.com",
            recipients_to=("elliot@example.com",),
            recipients_cc=(),
            recipients_bcc=(),
            sent_at=datetime(2026, 7, 18, 10, 30, tzinfo=UTC),
            received_at=None,
            message_id="<pimba@example.com>",
            body_text="The Pimba service was restored after the router change.",
        )
    )
    return store


class FakeProvider:
    def __init__(self, answer: GroundedAnswer) -> None:
        self.answer_value = answer
        self.calls = 0

    def answer(
        self,
        question: str,
        evidence: Sequence[EmailEvidence],
    ) -> GroundedAnswer:
        del question, evidence
        self.calls += 1
        return self.answer_value


class FailingProvider:
    def answer(
        self,
        question: str,
        evidence: Sequence[EmailEvidence],
    ) -> GroundedAnswer:
        del question, evidence
        raise RuntimeError("sensitive provider detail")


def test_build_bounded_context_caps_content_and_numbers_sources() -> None:
    evidence = tuple(_evidence(index, excerpt="x" * 1_200) for index in range(1, 6))

    context = build_bounded_context(evidence, max_characters=500)

    assert len(context) <= 500
    assert "SOURCE [1]" in context
    assert "SOURCE [2]" not in context


def test_grounded_instructions_require_sources_and_uncertainty() -> None:
    instructions = build_grounded_instructions("What happened?", "SOURCE [1]")

    assert "only the numbered email sources" in instructions
    assert "Do not invent" in instructions
    assert "evidence is insufficient" in instructions
    assert "SOURCE [1]" in instructions


def test_extractive_provider_returns_numbered_citations() -> None:
    answer = ExtractiveAnswerProvider().answer(
        "What happened?",
        (_evidence(1), _evidence(2)),
    )

    assert "[1]" in answer.text
    assert "[2]" in answer.text
    assert answer.cited_evidence_ids == (1, 2)
    assert not answer.insufficient_evidence


def test_extractive_provider_reports_insufficient_evidence() -> None:
    answer = ExtractiveAnswerProvider().answer("Unknown?", ())

    assert answer.insufficient_evidence
    assert answer.cited_evidence_ids == ()


def test_validate_grounded_answer_rejects_invalid_text_citation() -> None:
    answer = GroundedAnswer("Claim [99]", (1,))

    with pytest.raises(CitationValidationError, match="text citations"):
        validate_grounded_answer(answer, (_evidence(1),))


def test_validate_grounded_answer_rejects_undeclared_text_citation() -> None:
    answer = GroundedAnswer("Claim without citation", (1,))

    with pytest.raises(CitationValidationError, match="text citations"):
        validate_grounded_answer(answer, (_evidence(1),))


def test_validate_grounded_answer_rejects_invalid_citation() -> None:
    answer = GroundedAnswer("Unsupported [2]", (2,))

    with pytest.raises(CitationValidationError, match="invalid citation"):
        validate_grounded_answer(answer, (_evidence(1),))


def test_validate_grounded_answer_requires_citation() -> None:
    with pytest.raises(CitationValidationError, match="did not cite"):
        validate_grounded_answer(GroundedAnswer("Claim", ()), (_evidence(1),))


def test_answer_question_validates_fake_provider_citations(tmp_path: Path) -> None:
    store = _store_with_pimba_email(tmp_path)
    provider = FakeProvider(GroundedAnswer("Restored [1]", (1,)))

    result = answer_question(
        "What happened at Pimba?", RetrievalEngine.from_store(store), provider
    )

    assert provider.calls == 1
    assert result.answer.text == "Restored [1]"
    assert result.evidence[0].source_record_key == "pimba-email"


def test_answer_question_skips_provider_without_evidence(tmp_path: Path) -> None:
    store = _store_with_pimba_email(tmp_path)
    provider = FakeProvider(GroundedAnswer("Should not run", (1,)))

    result = answer_question("?!", RetrievalEngine.from_store(store), provider)

    assert provider.calls == 0
    assert result.answer.insufficient_evidence


def test_answer_question_hides_provider_failure_details(tmp_path: Path) -> None:
    store = _store_with_pimba_email(tmp_path)

    with pytest.raises(AnswerGenerationError, match="could not generate") as error:
        answer_question("Pimba", RetrievalEngine.from_store(store), FailingProvider())

    assert "sensitive provider detail" not in str(error.value)


def test_resolve_answer_provider_defaults_to_local_extractive() -> None:
    assert isinstance(resolve_answer_provider({}), ExtractiveAnswerProvider)
    assert isinstance(
        resolve_answer_provider({"EDN_LLM_PROVIDER": "disabled"}),
        DisabledAnswerProvider,
    )


def test_resolve_answer_provider_rejects_unapproved_provider() -> None:
    with pytest.raises(AnswerConfigurationError, match="Unsupported"):
        resolve_answer_provider({"EDN_LLM_PROVIDER": "cloud"})
