"""The date resolver is the part that must never guess."""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.dates import find_due_expression, resolve_due_expression
from app.models import DueStatus, ResolutionReason

MONDAY = datetime(2026, 9, 14, 10, 0)  # a Monday
FRIDAY = datetime(2026, 9, 18, 10, 0)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("сегодня", date(2026, 9, 14)),
        ("завтра", date(2026, 9, 15)),
        ("послезавтра", date(2026, 9, 16)),
        ("до пятницы", date(2026, 9, 18)),
        ("к среде", date(2026, 9, 16)),
        ("во вторник", date(2026, 9, 15)),
        ("через 3 дня", date(2026, 9, 17)),
        ("через 2 недели", date(2026, 9, 28)),
        ("через 1 месяц", date(2026, 10, 14)),
        ("до конца недели", date(2026, 9, 18)),
        ("до конца месяца", date(2026, 9, 30)),
        ("25 сентября", date(2026, 9, 25)),
        ("25-го сентября", date(2026, 9, 25)),
        ("до 25.09.2026", date(2026, 9, 25)),
        ("2026-10-01", date(2026, 10, 1)),
        ("01.10.26", date(2026, 10, 1)),
        ("tomorrow", date(2026, 9, 15)),
        ("by Friday", date(2026, 9, 18)),
        ("in 5 days", date(2026, 9, 19)),
        ("end of the month", date(2026, 9, 30)),
        ("Sep 25", date(2026, 9, 25)),
        ("September 25, 2026", date(2026, 9, 25)),
    ],
)
def test_resolves_to_exact_date(expression: str, expected: date) -> None:
    outcome = resolve_due_expression(expression, MONDAY)
    assert outcome.status is DueStatus.RESOLVED
    assert outcome.due_date == expected


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        (None, ResolutionReason.NO_DEADLINE),
        ("", ResolutionReason.NO_DEADLINE),
        ("   ", ResolutionReason.NO_DEADLINE),
        ("как получится", ResolutionReason.UNPARSEABLE),
        ("на следующей неделе", ResolutionReason.UNPARSEABLE),
        ("next week", ResolutionReason.UNPARSEABLE),
        ("в ближайшее время", ResolutionReason.UNPARSEABLE),
        ("скоро", ResolutionReason.UNPARSEABLE),
    ],
)
def test_refuses_to_invent_a_date(expression: str | None, reason: ResolutionReason) -> None:
    outcome = resolve_due_expression(expression, MONDAY)
    assert outcome.status is DueStatus.NEEDS_CONFIRMATION
    assert outcome.reason is reason
    assert outcome.due_date is None


def test_same_weekday_as_the_message_is_ambiguous() -> None:
    """'до пятницы' said on a Friday could mean today or next week — ask."""
    outcome = resolve_due_expression("до пятницы", FRIDAY)
    assert outcome.status is DueStatus.NEEDS_CONFIRMATION
    assert outcome.reason is ResolutionReason.AMBIGUOUS_WEEKDAY


def test_explicit_next_weekday_is_not_ambiguous() -> None:
    outcome = resolve_due_expression("в следующую пятницу", FRIDAY)
    assert outcome.status is DueStatus.RESOLVED
    assert outcome.due_date == date(2026, 9, 25)


def test_relative_expression_without_anchor_needs_confirmation() -> None:
    outcome = resolve_due_expression("завтра", None)
    assert outcome.reason is ResolutionReason.NO_ANCHOR


def test_absolute_date_needs_no_anchor() -> None:
    assert resolve_due_expression("2026-10-01", None).due_date == date(2026, 10, 1)


def test_yearless_date_just_in_the_past_is_ambiguous() -> None:
    outcome = resolve_due_expression("13 сентября", MONDAY)
    assert outcome.status is DueStatus.NEEDS_CONFIRMATION
    assert outcome.reason is ResolutionReason.AMBIGUOUS_YEAR


def test_yearless_date_well_in_the_past_rolls_to_next_year() -> None:
    assert resolve_due_expression("5 марта", MONDAY).due_date == date(2027, 3, 5)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("завтра до 18:00", time(18, 0)),
        ("в пятницу к 9:30", time(9, 30)),
        ("by Friday 5pm", time(17, 0)),
    ],
)
def test_extracts_the_clock_time(expression: str, expected: time) -> None:
    assert resolve_due_expression(expression, MONDAY).due_time == expected


def test_impossible_date_is_not_silently_shifted() -> None:
    assert resolve_due_expression("31.02.2026", MONDAY).status is DueStatus.NEEDS_CONFIRMATION


def test_leap_day_resolves() -> None:
    assert resolve_due_expression("29.02.2028", MONDAY).due_date == date(2028, 2, 29)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Отправлю договор завтра до 18:00.", "завтра до 18:00"),
        ("Вернёмся с расчётом до пятницы.", "до пятницы"),
        ("Исправим до 25 сентября.", "до 25 сентября"),
        ("I will send it by Friday.", "by Friday"),
        ("Посмотрю и отпишусь.", None),
    ],
)
def test_find_due_expression(sentence: str, expected: str | None) -> None:
    assert find_due_expression(sentence) == expected
