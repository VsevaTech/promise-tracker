"""iCalendar export.

Only commitments with a resolved date are exportable — a reminder with a guessed
date is worse than no reminder, so unresolved ones are rejected by the caller.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from icalendar import Alarm, Calendar, Event

from app.config import Settings
from app.models import Commitment

PRODID = "-//Promise Tracker//promise-tracker//EN"


class NothingToExport(ValueError):
    """Raised when no commitment in the selection carries a date."""


def _summary(commitment: Commitment) -> str:
    who = commitment.speaker.strip()
    what = commitment.what.strip()
    return f"{who}: {what}" if who else what


def _description(commitment: Commitment) -> str:
    lines = []
    if commitment.speaker:
        lines.append(f"Promised by: {commitment.speaker}")
    if commitment.recipient:
        lines.append(f"Promised to: {commitment.recipient}")
    if commitment.due_expression:
        lines.append(f"Deadline wording: {commitment.due_expression}")
    if commitment.anchor:
        lines.append(f"Said at: {commitment.anchor:%Y-%m-%d %H:%M}")
    if commitment.source_quote:
        lines.append("")
        lines.append(f"Source quote: “{commitment.source_quote}”")
    lines.append("")
    lines.append("Extracted by Promise Tracker.")
    return "\n".join(lines)


def build_calendar(
    commitments: list[Commitment],
    settings: Settings,
    now: datetime | None = None,
) -> Calendar:
    exportable = [c for c in commitments if c.due_date is not None]
    if not exportable:
        raise NothingToExport("None of the selected commitments has a confirmed date.")

    stamp = now or datetime.now()
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Promises")

    for commitment in exportable:
        start = datetime.combine(commitment.due_date, commitment.due_time or settings.due_time)
        event = Event()
        event.add("uid", f"{commitment.id}@promise-tracker")
        event.add("dtstamp", stamp)
        event.add("dtstart", start)
        event.add("dtend", start + timedelta(minutes=settings.event_duration_minutes))
        event.add("summary", _summary(commitment))
        event.add("description", _description(commitment))
        event.add("categories", ["PROMISE"])

        if settings.alarm_minutes_before:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", _summary(commitment))
            alarm.add("trigger", timedelta(minutes=-settings.alarm_minutes_before))
            event.add_component(alarm)

        cal.add_component(event)
    return cal


def render_ics(
    commitments: list[Commitment], settings: Settings, now: datetime | None = None
) -> bytes:
    return build_calendar(commitments, settings, now).to_ical()
