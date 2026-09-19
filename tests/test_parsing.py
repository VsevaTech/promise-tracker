from __future__ import annotations

from datetime import datetime

from app.parsing import parse_conversation, parse_timestamp


def test_parses_bracketed_export() -> None:
    messages = parse_conversation("[2026-09-14 10:32] Anna Petrova: Когда будет договор?")
    assert len(messages) == 1
    assert messages[0].author == "Anna Petrova"
    assert messages[0].sent_at == datetime(2026, 9, 14, 10, 32)
    assert messages[0].text == "Когда будет договор?"


def test_parses_several_header_shapes() -> None:
    raw = (
        "[2026-09-14 10:32] Anna: a\n"
        "Sergey (14.09.2026 10:40): b\n"
        "2026-09-14 11:02 - Anna: c\n"
        "Michael, 14.09.2026 11:10: d\n"
        "Sergey: e\n"
    )
    messages = parse_conversation(raw)
    assert [m.author for m in messages] == ["Anna", "Sergey", "Anna", "Michael", "Sergey"]
    assert [m.text for m in messages] == list("abcde")


def test_continuation_lines_join_the_previous_message() -> None:
    messages = parse_conversation("[2026-09-14 10:32] Anna: first line\nsecond line")
    assert len(messages) == 1
    assert messages[0].text == "first line\nsecond line"


def test_message_without_timestamp_inherits_the_last_one() -> None:
    messages = parse_conversation("[2026-09-14 10:32] Anna: a\nSergey: b")
    assert messages[1].sent_at == datetime(2026, 9, 14, 10, 32)


def test_unstructured_text_falls_back_to_the_reference_date() -> None:
    reference = datetime(2026, 9, 14)
    messages = parse_conversation("прислать счёт завтра", reference=reference)
    assert len(messages) == 1
    assert messages[0].sent_at == reference


def test_empty_input_yields_no_messages() -> None:
    assert parse_conversation("   \n\n") == []


def test_indexes_are_sequential(conversation_ru: str) -> None:
    messages = parse_conversation(conversation_ru)
    assert len(messages) == 20
    assert [m.index for m in messages] == list(range(20))


def test_unknown_timestamp_returns_none() -> None:
    assert parse_timestamp("not a date") is None
    assert parse_timestamp("32.13.2026") is None
