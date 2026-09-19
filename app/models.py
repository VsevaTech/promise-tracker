"""Pydantic models: the extraction contract and the resolved commitment."""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum

from pydantic import BaseModel, Field


class Message(BaseModel):
    """One parsed message of a conversation."""

    index: int = Field(description="0-based position in the conversation")
    author: str = Field(default="", description="Message author as written in the source")
    sent_at: datetime | None = Field(
        default=None, description="Timestamp parsed from the source, if present"
    )
    text: str = Field(default="")

    def render(self) -> str:
        stamp = self.sent_at.strftime("%Y-%m-%d %H:%M") if self.sent_at else "no timestamp"
        return f"[{self.index}] ({stamp}) {self.author or 'unknown'}: {self.text}"


class ExtractedCommitment(BaseModel):
    """Raw AI/rule output.

    The extractor is deliberately forbidden from doing date arithmetic: it may only
    copy the deadline wording (``due_expression``) verbatim from the message. All
    calendar math happens in :mod:`app.dates`.
    """

    speaker: str = Field(default="", description="Who made the promise")
    recipient: str | None = Field(default=None, description="Who the promise was made to")
    what: str = Field(description="What was promised, one short sentence")
    due_expression: str | None = Field(
        default=None,
        description=(
            "Deadline wording copied verbatim from the message "
            "('завтра', 'до пятницы', '25 сентября'). null if the message names no deadline. "
            "Never compute or invent a calendar date here."
        ),
    )
    source_quote: str = Field(description="Exact fragment of the message the promise comes from")
    message_index: int | None = Field(
        default=None, description="Index of the source message in the conversation"
    )


class ExtractionResult(BaseModel):
    """Top-level structured output returned by the extractor."""

    commitments: list[ExtractedCommitment] = Field(default_factory=list)


class DueStatus(StrEnum):
    RESOLVED = "resolved"
    NEEDS_CONFIRMATION = "needs_confirmation"


class ResolutionReason(StrEnum):
    OK = "ok"
    NO_DEADLINE = "no_deadline"
    UNPARSEABLE = "unparseable"
    AMBIGUOUS_WEEKDAY = "ambiguous_weekday"
    AMBIGUOUS_YEAR = "ambiguous_year"
    NO_ANCHOR = "no_anchor"
    NOT_IN_SOURCE = "not_in_source"


REASON_TEXT: dict[ResolutionReason, str] = {
    ResolutionReason.OK: "Deadline resolved from the quoted wording.",
    ResolutionReason.NO_DEADLINE: "The message promises something but names no deadline.",
    ResolutionReason.UNPARSEABLE: "The deadline wording could not be resolved to a single date.",
    ResolutionReason.AMBIGUOUS_WEEKDAY: (
        "The weekday named is the same as the day the message was sent — "
        "this week or next is undecidable."
    ),
    ResolutionReason.AMBIGUOUS_YEAR: (
        "The date has no year and falls in the past relative to the message."
    ),
    ResolutionReason.NO_ANCHOR: (
        "The wording is relative but the source message has no timestamp to count from."
    ),
    ResolutionReason.NOT_IN_SOURCE: (
        "The deadline wording returned by the extractor does not appear in the conversation, "
        "so it was discarded rather than trusted."
    ),
}


class Commitment(BaseModel):
    """An extracted commitment after deterministic date resolution."""

    id: str
    speaker: str = ""
    recipient: str | None = None
    what: str
    source_quote: str
    due_expression: str | None = None
    message_index: int | None = None
    anchor: datetime | None = None

    due_date: date | None = None
    due_time: time | None = None
    status: DueStatus = DueStatus.NEEDS_CONFIRMATION
    reason: ResolutionReason = ResolutionReason.NO_DEADLINE

    @property
    def reason_text(self) -> str:
        return REASON_TEXT[self.reason]

    @property
    def needs_confirmation(self) -> bool:
        return self.status is DueStatus.NEEDS_CONFIRMATION
