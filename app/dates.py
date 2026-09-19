"""Deterministic deadline resolution.

Nothing in this module calls an AI model. The extractor hands over the deadline
*wording* copied from the message; everything below turns that wording into a
calendar date with plain Python, so the result is reproducible and unit-tested.

Whenever the wording cannot be resolved to exactly one date, the resolver refuses
to guess and returns ``NEEDS_CONFIRMATION`` with a machine-readable reason.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.models import DueStatus, ResolutionReason

# --- vocabulary ------------------------------------------------------------

WEEKDAYS: dict[str, int] = {
    # Russian, normalised to a stem so most inflections match.
    "понедельник": 0,
    "вторник": 1,
    "сред": 2,
    "четверг": 3,
    "пятниц": 4,
    "суббот": 5,
    "воскресень": 6,
    # English
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

MONTHS: dict[str, int] = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MONTH_ALTERNATION = "|".join(sorted(MONTHS, key=len, reverse=True))
_WEEKDAY_ALTERNATION = "|".join(sorted(WEEKDAYS, key=len, reverse=True))

# How far in the past a year-less date may fall before we stop assuming
# "the speaker meant this year" and ask the user instead.
PAST_TOLERANCE_DAYS = 2


@dataclass(frozen=True)
class Resolution:
    """Outcome of resolving one deadline expression."""

    status: DueStatus
    reason: ResolutionReason
    due_date: date | None = None
    due_time: time | None = None

    @classmethod
    def ok(cls, due_date: date, due_time: time | None = None) -> Resolution:
        return cls(DueStatus.RESOLVED, ResolutionReason.OK, due_date, due_time)

    @classmethod
    def unresolved(cls, reason: ResolutionReason) -> Resolution:
        return cls(DueStatus.NEEDS_CONFIRMATION, reason)


def _normalize(expression: str) -> str:
    text = expression.lower().replace("ё", "е").strip()
    text = re.sub(r"[«»\"'()\[\]]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .,;:!?-")


def _extract_time(text: str) -> tuple[str, time | None]:
    """Pull an explicit clock time out of the expression, if present."""
    # Guarded against date-like tokens: "01.10.26" must not read as 01:10.
    match = re.search(r"(?<![\d.])([01]?\d|2[0-3])[:.]([0-5]\d)(?![\d.])", text)
    if match:
        found = time(int(match.group(1)), int(match.group(2)))
        return text[: match.start()] + " " + text[match.end() :], found
    match = re.search(r"\b(\d{1,2})\s*(am|pm)\b", text)
    if match:
        hour = int(match.group(1)) % 12
        if match.group(2) == "pm":
            hour += 12
        return text[: match.start()] + " " + text[match.end() :], time(hour, 0)
    return text, None


def _lookup_stem(text: str, table: dict[str, int]) -> int | None:
    for stem in sorted(table, key=len, reverse=True):
        if stem in text:
            return table[stem]
    return None


def _month_from_name(name: str) -> int | None:
    name = name.lower()
    for stem in sorted(MONTHS, key=len, reverse=True):
        if name.startswith(stem):
            return MONTHS[stem]
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_yearless(candidate_month: int, candidate_day: int, anchor: date) -> Resolution:
    """A date with no year: assume the anchor's year, roll forward if needed."""
    this_year = _safe_date(anchor.year, candidate_month, candidate_day)
    if this_year is None:
        return Resolution.unresolved(ResolutionReason.UNPARSEABLE)
    if this_year >= anchor:
        return Resolution.ok(this_year)
    # In the past. A day or two back is a typo-ish edge we refuse to guess on;
    # anything older is almost certainly next year.
    if (anchor - this_year).days <= PAST_TOLERANCE_DAYS:
        return Resolution.unresolved(ResolutionReason.AMBIGUOUS_YEAR)
    next_year = _safe_date(anchor.year + 1, candidate_month, candidate_day)
    if next_year is None:
        return Resolution.unresolved(ResolutionReason.UNPARSEABLE)
    return Resolution.ok(next_year)


def _end_of_week(anchor: date) -> date:
    """Friday of the anchor's week; if the anchor is past Friday, the next one."""
    delta = 4 - anchor.weekday()
    if delta < 0:
        delta += 7
    return anchor + timedelta(days=delta)


def _end_of_month(anchor: date) -> date:
    return date(anchor.year, anchor.month, calendar.monthrange(anchor.year, anchor.month)[1])


def resolve_due_expression(expression: str | None, anchor: datetime | None) -> Resolution:
    """Turn a deadline wording into a date, or refuse to.

    ``anchor`` is the moment the source message was sent — every relative
    expression ("завтра", "через 3 дня") is counted from it.
    """
    if expression is None or not expression.strip():
        return Resolution.unresolved(ResolutionReason.NO_DEADLINE)

    text, clock = _extract_time(_normalize(expression))
    if not text.strip():
        return Resolution.unresolved(ResolutionReason.UNPARSEABLE)

    # --- fully qualified dates need no anchor ------------------------------
    iso = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if iso:
        found = _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        return (
            Resolution.ok(found, clock)
            if found
            else Resolution.unresolved(ResolutionReason.UNPARSEABLE)
        )

    dmy = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b", text)
    if dmy:
        year = int(dmy.group(3))
        year += 2000 if year < 100 else 0
        found = _safe_date(year, int(dmy.group(2)), int(dmy.group(1)))
        return (
            Resolution.ok(found, clock)
            if found
            else Resolution.unresolved(ResolutionReason.UNPARSEABLE)
        )

    anchor_date = anchor.date() if anchor else None

    # --- "25 сентября" / "сентября 25" / "sep 25" --------------------------
    named = re.search(rf"\b(\d{{1,2}})\s*(?:-?го)?\s+({_MONTH_ALTERNATION})[a-zа-я]*", text)
    if not named:
        named_rev = re.search(rf"\b({_MONTH_ALTERNATION})[a-zа-я]*\.?\s+(\d{{1,2}})\b", text)
        if named_rev:
            day, month_name = named_rev.group(2), named_rev.group(1)
        else:
            day = month_name = None
    else:
        day, month_name = named.group(1), named.group(2)

    if day and month_name:
        month = _month_from_name(month_name)
        if month is None:
            return Resolution.unresolved(ResolutionReason.UNPARSEABLE)
        year_hint = re.search(r"\b(20\d{2})\b", text)
        if year_hint:
            found = _safe_date(int(year_hint.group(1)), month, int(day))
            return (
                Resolution.ok(found, clock)
                if found
                else Resolution.unresolved(ResolutionReason.UNPARSEABLE)
            )
        if anchor_date is None:
            return Resolution.unresolved(ResolutionReason.NO_ANCHOR)
        resolved = _resolve_yearless(month, int(day), anchor_date)
        return (
            Resolution.ok(resolved.due_date, clock)
            if resolved.status is DueStatus.RESOLVED
            else resolved
        )

    # --- everything below is relative and needs an anchor ------------------
    if anchor_date is None:
        return Resolution.unresolved(ResolutionReason.NO_ANCHOR)

    if re.search(r"\b(сегодня|today)\b", text):
        return Resolution.ok(anchor_date, clock)
    if re.search(r"\b(послезавтра|day after tomorrow)\b", text):
        return Resolution.ok(anchor_date + timedelta(days=2), clock)
    if re.search(r"\b(завтра|tomorrow)\b", text):
        return Resolution.ok(anchor_date + timedelta(days=1), clock)

    delta = re.search(
        r"\b(?:через|in)\s+(\d{1,3})\s*(дн|день|дня|дней|недел|week|day|month|месяц)",
        text,
    )
    if delta:
        amount, unit = int(delta.group(1)), delta.group(2)
        if unit.startswith(("недел", "week")):
            return Resolution.ok(anchor_date + timedelta(weeks=amount), clock)
        if unit.startswith(("месяц", "month")):
            month_index = anchor_date.month - 1 + amount
            year = anchor_date.year + month_index // 12
            month = month_index % 12 + 1
            day = min(anchor_date.day, calendar.monthrange(year, month)[1])
            return Resolution.ok(date(year, month, day), clock)
        return Resolution.ok(anchor_date + timedelta(days=amount), clock)

    if re.search(r"(конц[аеу]\s+недели|end of (the )?week)", text):
        return Resolution.ok(_end_of_week(anchor_date), clock)
    if re.search(r"(конц[аеу]\s+месяца|end of (the )?month)", text):
        return Resolution.ok(_end_of_month(anchor_date), clock)
    if re.search(r"(следующ\w*\s+недел|next week)", text) and not re.search(
        rf"({_WEEKDAY_ALTERNATION})", text
    ):
        # "next week" alone names a week, not a day.
        return Resolution.unresolved(ResolutionReason.UNPARSEABLE)

    weekday = _lookup_stem(text, WEEKDAYS)
    if weekday is not None:
        explicit_next = bool(re.search(r"(следующ|next|на следующей)", text))
        delta_days = (weekday - anchor_date.weekday()) % 7
        if delta_days == 0 and not explicit_next:
            # "до пятницы" sent on a Friday: this one or the next is undecidable.
            return Resolution.unresolved(ResolutionReason.AMBIGUOUS_WEEKDAY)
        if explicit_next:
            delta_days = delta_days + 7 if delta_days <= 0 else delta_days
            if (anchor_date + timedelta(days=delta_days)).isocalendar()[1] == (
                anchor_date.isocalendar()[1]
            ):
                delta_days += 7
        return Resolution.ok(anchor_date + timedelta(days=delta_days), clock)

    return Resolution.unresolved(ResolutionReason.UNPARSEABLE)


# --- deadline wording detection -------------------------------------------
# Used by the rule-based extractor (and by tests) to locate the deadline phrase
# inside a sentence. The AI extractor copies the wording itself instead.

_DUE_PATTERNS: tuple[str, ...] = (
    rf"\b(?:до|к|по|на|by|before|until|on)?\s*\d{{1,2}}\s*(?:-?го)?\s+(?:{_MONTH_ALTERNATION})[a-zа-я]*(?:\s+20\d{{2}})?",
    rf"\b(?:{_MONTH_ALTERNATION})[a-z]*\.?\s+\d{{1,2}}(?:,?\s+20\d{{2}})?",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[./]\d{1,2}[./](?:\d{4}|\d{2})\b",
    r"\b(?:послезавтра|завтра|сегодня|day after tomorrow|tomorrow|today)\b",
    r"\b(?:через|in)\s+\d{1,3}\s*(?:дн\w*|день|недел\w*|месяц\w*|days?|weeks?|months?)",
    r"(?:до|к)\s+конц[аеу]\s+(?:недели|месяца)",
    r"(?:by|before)\s+the\s+end\s+of\s+(?:the\s+)?(?:week|month)",
    rf"\b(?:до|к|в|во|на|by|before|on|next)\s+(?:следующ\w+\s+)?(?:{_WEEKDAY_ALTERNATION})[a-zа-я]*",
    r"\b(?:на\s+следующей\s+неделе|next\s+week)\b",
)

_TIME_SUFFIX = r"(?:\s*(?:до|к|at|by)?\s*(?:[01]?\d|2[0-3])[:.][0-5]\d)?"


def find_due_expression(text: str) -> str | None:
    """Return the first deadline wording found in ``text``, verbatim."""
    normalized = text.replace("ё", "е")
    best: tuple[int, str] | None = None
    for pattern in _DUE_PATTERNS:
        match = re.search(pattern + _TIME_SUFFIX, normalized, flags=re.IGNORECASE)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), text[match.start() : match.end()].strip(" .,;:"))
    return best[1] if best else None
