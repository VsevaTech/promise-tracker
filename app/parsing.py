"""Conversation parsing: raw pasted text -> list of Message objects.

Chat exports differ wildly, so the parser recognises a handful of common shapes
and degrades gracefully: a line it cannot attribute is appended to the previous
message, and a conversation with no recognisable structure becomes a single
message anchored at the reference date.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.models import Message

_TS_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})", "ymd"),
    (r"(\d{1,2})\.(\d{1,2})\.(\d{4})[ ,]+(\d{1,2}):(\d{2})", "dmy"),
    (r"(\d{1,2})/(\d{1,2})/(\d{4})[ ,]+(\d{1,2}):(\d{2})", "mdy"),
    (r"(\d{4})-(\d{2})-(\d{2})", "ymd_only"),
    (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "dmy_only"),
)

# [stamp] Author: text   |   stamp - Author: text   |   stamp, Author: text
_HEADERS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*[\[(]\s*(?P<stamp>[^\])]{6,40})\s*[\])]\s*"
        r"(?P<author>[^:]{1,60}?)\s*:\s*(?P<text>.*)$"
    ),
    re.compile(
        r"^\s*(?P<stamp>\d[\d\-/.: T,]{8,30}?)\s*[-—–]\s*"
        r"(?P<author>[^:]{1,60}?)\s*:\s*(?P<text>.*)$"
    ),
    re.compile(
        r"^\s*(?P<author>[^:\d][^:]{0,59}?)\s*[\[(]\s*(?P<stamp>[^\])]{6,40})\s*[\])]"
        r"\s*:\s*(?P<text>.*)$"
    ),
    re.compile(
        r"^\s*(?P<author>[^:]{1,60}?)\s*,\s*"
        r"(?P<stamp>\d[\d\-/.: T]{8,30})\s*:\s*(?P<text>.*)$"
    ),
    re.compile(r"^\s*(?P<author>[A-Za-zА-Яа-яЁё][\w .'’\-]{0,59}?)\s*:\s+(?P<text>.+)$"),
)


def parse_timestamp(raw: str) -> datetime | None:
    """Best-effort timestamp parsing; returns None rather than guessing."""
    raw = raw.strip()
    for pattern, kind in _TS_PATTERNS:
        match = re.search(pattern, raw)
        if not match:
            continue
        parts = [int(p) for p in match.groups()]
        try:
            if kind == "ymd":
                return datetime(parts[0], parts[1], parts[2], parts[3], parts[4])
            if kind == "dmy":
                return datetime(parts[2], parts[1], parts[0], parts[3], parts[4])
            if kind == "mdy":
                return datetime(parts[2], parts[0], parts[1], parts[3], parts[4])
            if kind == "ymd_only":
                return datetime(parts[0], parts[1], parts[2])
            if kind == "dmy_only":
                return datetime(parts[2], parts[1], parts[0])
        except ValueError:
            return None
    return None


def parse_conversation(raw: str, reference: datetime | None = None) -> list[Message]:
    """Split pasted text into messages.

    Messages without their own timestamp inherit the last seen timestamp, and
    failing that the ``reference`` moment supplied by the user.
    """
    messages: list[Message] = []
    last_seen = reference

    for line in raw.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue

        matched = None
        for pattern in _HEADERS:
            matched = pattern.match(line)
            if matched:
                break

        if matched is None:
            if messages:
                messages[-1].text = f"{messages[-1].text}\n{line.strip()}".strip()
            else:
                messages.append(Message(index=0, author="", sent_at=last_seen, text=line.strip()))
            continue

        groups = matched.groupdict()
        stamp = parse_timestamp(groups.get("stamp") or "") if groups.get("stamp") else None
        if stamp is not None:
            last_seen = stamp
        messages.append(
            Message(
                index=len(messages),
                author=(groups.get("author") or "").strip(),
                sent_at=stamp or last_seen,
                text=(groups.get("text") or "").strip(),
            )
        )

    if not messages and raw.strip():
        messages.append(Message(index=0, author="", sent_at=reference, text=raw.strip()))
    return messages


def render_conversation(messages: list[Message]) -> str:
    return "\n".join(message.render() for message in messages)
