"""End-to-end extraction: parse -> extract -> deterministic dates."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.config import Settings
from app.extractor import extract, resolve
from app.models import (
    DueStatus,
    ExtractedCommitment,
    ExtractionResult,
    ResolutionReason,
)
from app.parsing import parse_conversation
from app.services import ai

REFERENCE = datetime(2026, 9, 14)


def test_demo_conversation_yields_three_commitments(conversation_ru: str, settings) -> None:
    report = extract(conversation_ru, reference=REFERENCE, settings=settings)
    assert len(report.messages) == 20
    assert len(report.commitments) == 3
    assert report.resolved_count == 2
    assert report.needs_confirmation_count == 1

    first, second, third = report.commitments
    assert first.due_date == date(2026, 9, 15)  # "завтра" from a Monday message
    assert first.due_time.hour == 18
    assert second.due_date == date(2026, 9, 18)  # "до пятницы"
    assert third.needs_confirmation
    assert third.reason is ResolutionReason.NO_DEADLINE


def test_english_conversation(conversation_en: str, settings) -> None:
    report = extract(conversation_en, reference=REFERENCE, settings=settings)
    assert [c.due_date for c in report.commitments] == [date(2026, 9, 18), date(2026, 9, 25)]


def test_every_commitment_carries_a_quote(conversation_ru: str, settings) -> None:
    report = extract(conversation_ru, reference=REFERENCE, settings=settings)
    for commitment in report.commitments:
        assert commitment.source_quote
        assert commitment.source_quote in conversation_ru


def test_empty_conversation(settings) -> None:
    report = extract("   ", reference=REFERENCE, settings=settings)
    assert report.commitments == []
    assert report.engine == "none"


def test_invented_deadline_is_discarded() -> None:
    """A model that ignores the rules cannot smuggle a date past the resolver."""
    messages = parse_conversation("[2026-09-14 10:00] S: Исправим ошибку в отчёте.")
    extraction = ExtractionResult(
        commitments=[
            ExtractedCommitment(
                what="Исправить отчёт",
                due_expression="2026-12-31",  # never said by anyone
                source_quote="Исправим ошибку в отчёте.",
                message_index=0,
            )
        ]
    )
    [commitment] = resolve(extraction, messages)
    assert commitment.status is DueStatus.NEEDS_CONFIRMATION
    assert commitment.reason is ResolutionReason.NOT_IN_SOURCE
    assert commitment.due_date is None
    assert commitment.due_expression is None


def test_quoted_deadline_is_resolved_by_python_not_the_model() -> None:
    messages = parse_conversation("[2026-09-14 10:00] S: Отправлю счёт через 2 недели.")
    extraction = ExtractionResult(
        commitments=[
            ExtractedCommitment(
                what="Отправить счёт",
                due_expression="через 2 недели",
                source_quote="Отправлю счёт через 2 недели.",
                message_index=0,
            )
        ]
    )
    [commitment] = resolve(extraction, messages)
    assert commitment.due_date == date(2026, 9, 28)


def test_falls_back_to_rules_when_gemini_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, conversation_ru: str
) -> None:
    def _boom(messages, settings):
        raise ai.AIUnavailable("Gemini request failed: ResourceExhausted")

    monkeypatch.setattr("app.extractor.extract_with_gemini", _boom)
    configured = Settings(gemini_api_key="key", gemini_model="model", extractor="gemini")

    report = extract(conversation_ru, reference=REFERENCE, settings=configured)
    assert report.engine == "rules"
    assert "Falling back" in report.notice
    assert len(report.commitments) == 3  # the app still works


def test_gemini_output_is_used_when_available(
    monkeypatch: pytest.MonkeyPatch, conversation_ru: str
) -> None:
    def _fake(messages, settings):
        return ExtractionResult(
            commitments=[
                ExtractedCommitment(
                    speaker="Сергей Орлов",
                    recipient="Анна Петрова",
                    what="Отправить договор",
                    due_expression="завтра до 18:00",
                    source_quote="Отправлю договор завтра до 18:00.",
                    message_index=3,
                )
            ]
        )

    monkeypatch.setattr("app.extractor.extract_with_gemini", _fake)
    configured = Settings(gemini_api_key="key", gemini_model="gemini-x", extractor="gemini")
    report = extract(conversation_ru, reference=REFERENCE, settings=configured)

    assert report.engine == "gemini (gemini-x)"
    assert report.notice is None
    assert report.commitments[0].due_date == date(2026, 9, 15)


def test_conversation_is_truncated_to_the_configured_limit(settings) -> None:
    tiny = settings.model_copy(update={"max_conversation_chars": 40})
    report = extract("[2026-09-14 10:00] S: " + "Отправлю договор завтра. " * 50, settings=tiny)
    assert len(report.messages) == 1
    assert len(report.messages[0].text) < 60
