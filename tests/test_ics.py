from __future__ import annotations

from datetime import date, datetime, time

import pytest
from icalendar import Calendar

from app.config import Settings
from app.extractor import extract
from app.ics import NothingToExport, render_ics
from app.models import Commitment, DueStatus, ResolutionReason


def _commitment(**overrides) -> Commitment:
    base = {
        "id": "c0-abc12345",
        "speaker": "Сергей Орлов",
        "recipient": "Анна Петрова",
        "what": "Отправить договор",
        "source_quote": "Отправлю договор завтра до 18:00.",
        "due_expression": "завтра до 18:00",
        "anchor": datetime(2026, 9, 14, 10, 7),
        "due_date": date(2026, 9, 15),
        "due_time": time(18, 0),
        "status": DueStatus.RESOLVED,
        "reason": ResolutionReason.OK,
    }
    base.update(overrides)
    return Commitment(**base)


def test_event_carries_the_confirmed_moment(settings: Settings) -> None:
    cal = Calendar.from_ical(render_ics([_commitment()], settings))
    [event] = cal.walk("VEVENT")
    assert event["dtstart"].dt == datetime(2026, 9, 15, 18, 0)
    assert "Сергей Орлов" in str(event["summary"])
    assert "Отправлю договор завтра до 18:00." in str(event["description"])


def test_default_time_is_used_when_none_was_stated(settings: Settings) -> None:
    cal = Calendar.from_ical(render_ics([_commitment(due_time=None)], settings))
    [event] = cal.walk("VEVENT")
    assert event["dtstart"].dt.time() == settings.due_time


def test_alarm_is_attached(settings: Settings) -> None:
    cal = Calendar.from_ical(render_ics([_commitment()], settings))
    assert cal.walk("VALARM")


def test_alarm_can_be_switched_off(settings: Settings) -> None:
    quiet = settings.model_copy(update={"alarm_minutes_before": 0})
    assert not Calendar.from_ical(render_ics([_commitment()], quiet)).walk("VALARM")


def test_undated_commitments_are_never_exported(settings: Settings) -> None:
    undated = _commitment(
        due_date=None,
        due_time=None,
        status=DueStatus.NEEDS_CONFIRMATION,
        reason=ResolutionReason.NO_DEADLINE,
    )
    with pytest.raises(NothingToExport):
        render_ics([undated], settings)


def test_undated_commitments_are_skipped_in_a_mixed_selection(settings: Settings) -> None:
    undated = _commitment(
        id="c1-def",
        due_date=None,
        status=DueStatus.NEEDS_CONFIRMATION,
        reason=ResolutionReason.NO_DEADLINE,
    )
    cal = Calendar.from_ical(render_ics([_commitment(), undated], settings))
    assert len(cal.walk("VEVENT")) == 1


def test_uids_are_unique(settings: Settings) -> None:
    cal = Calendar.from_ical(render_ics([_commitment(), _commitment(id="c1-xyz98765")], settings))
    uids = {str(event["uid"]) for event in cal.walk("VEVENT")}
    assert len(uids) == 2


def test_demo_conversation_produces_two_reminders(conversation_ru: str, settings: Settings) -> None:
    report = extract(conversation_ru, reference=datetime(2026, 9, 14), settings=settings)
    cal = Calendar.from_ical(render_ics(report.commitments, settings))
    starts = sorted(event["dtstart"].dt for event in cal.walk("VEVENT"))
    assert starts == [datetime(2026, 9, 15, 18, 0), datetime(2026, 9, 18, 9, 0)]
