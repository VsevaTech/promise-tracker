from __future__ import annotations

import pytest

from app.parsing import parse_conversation
from app.services.rules import extract_commitments


def _extract(text: str):
    return extract_commitments(parse_conversation(f"[2026-09-14 10:00] Sergey: {text}")).commitments


@pytest.mark.parametrize(
    "sentence",
    [
        "Отправлю договор завтра до 18:00.",
        "Вернёмся с расчётом до пятницы.",
        "Исправим расхождение в отчёте.",
        "I will send the revised quote by Friday.",
        "We'll return the completed questionnaire on 25 September.",
    ],
)
def test_recognises_commitments(sentence: str) -> None:
    assert _extract(sentence), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "Когда будет договор?",
        "Постараюсь посмотреть логи до созвона, но не обещаю.",
        "Может быть, отправлю завтра.",
        "Проверка документов уже пройдена.",
        "I can't promise a fix date today.",
        "Maybe we'll look at it next week.",
    ],
)
def test_ignores_non_commitments(sentence: str) -> None:
    assert not _extract(sentence), sentence


def test_quote_is_verbatim() -> None:
    [found] = _extract("Отправлю договор завтра до 18:00.")
    assert found.source_quote == "Отправлю договор завтра до 18:00."
    assert found.due_expression == "завтра до 18:00"


def test_recipient_is_the_previous_speaker() -> None:
    raw = "[2026-09-14 10:00] Anna: Когда договор?\n[2026-09-14 10:05] Sergey: Отправлю завтра."
    [found] = extract_commitments(parse_conversation(raw)).commitments
    assert found.speaker == "Sergey"
    assert found.recipient == "Anna"
