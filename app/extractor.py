"""Orchestration: conversation text -> resolved commitments.

Pipeline: parse -> extract (Gemini or rules) -> deterministic date resolution.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.config import Settings, get_settings
from app.dates import Resolution, resolve_due_expression
from app.models import (
    Commitment,
    DueStatus,
    ExtractionResult,
    Message,
    ResolutionReason,
)
from app.parsing import parse_conversation
from app.services import rules
from app.services.ai import AIUnavailable, extract_with_gemini

logger = logging.getLogger(__name__)


@dataclass
class ExtractionReport:
    commitments: list[Commitment] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    engine: str = "rules"
    notice: str | None = None

    @property
    def resolved_count(self) -> int:
        return sum(1 for c in self.commitments if not c.needs_confirmation)

    @property
    def needs_confirmation_count(self) -> int:
        return sum(1 for c in self.commitments if c.needs_confirmation)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def _grounded(expression: str | None, haystack: str) -> bool:
    """True when the wording really occurs in the conversation.

    The extractor is instructed to copy the deadline wording verbatim. If what
    comes back is not in the text, it was invented — we drop it instead of
    turning a hallucination into a calendar entry.
    """
    if not expression:
        return True
    return _normalize(expression) in haystack


def _commitment_id(index: int, quote: str) -> str:
    digest = hashlib.sha1(quote.encode("utf-8")).hexdigest()[:8]
    return f"c{index}-{digest}"


def resolve(extraction: ExtractionResult, messages: list[Message]) -> list[Commitment]:
    """Attach deterministic dates to raw extractions."""
    by_index = {message.index: message for message in messages}
    haystack = _normalize(" ".join(message.text for message in messages))
    resolved: list[Commitment] = []

    for position, raw in enumerate(extraction.commitments):
        source = by_index.get(raw.message_index) if raw.message_index is not None else None
        anchor = source.sent_at if source else None
        if _grounded(raw.due_expression, haystack):
            outcome = resolve_due_expression(raw.due_expression, anchor)
        else:
            logger.info("Discarding an ungrounded deadline expression from the extractor.")
            raw = raw.model_copy(update={"due_expression": None})
            outcome = Resolution(
                status=DueStatus.NEEDS_CONFIRMATION, reason=ResolutionReason.NOT_IN_SOURCE
            )
        resolved.append(
            Commitment(
                id=_commitment_id(position, raw.source_quote or raw.what),
                speaker=raw.speaker,
                recipient=raw.recipient,
                what=raw.what,
                source_quote=raw.source_quote,
                due_expression=raw.due_expression,
                message_index=raw.message_index,
                anchor=anchor,
                due_date=outcome.due_date,
                due_time=outcome.due_time,
                status=outcome.status,
                reason=outcome.reason,
            )
        )
    return resolved


def extract(
    raw_text: str,
    reference: datetime | None = None,
    settings: Settings | None = None,
) -> ExtractionReport:
    settings = settings or get_settings()
    reference = reference or datetime.now()

    text = raw_text[: settings.max_conversation_chars]
    messages = parse_conversation(text, reference=reference)
    if not messages:
        return ExtractionReport(messages=[], engine="none", notice="The conversation is empty.")

    engine = "rules"
    notice: str | None = None
    extraction: ExtractionResult | None = None

    if settings.gemini_enabled:
        try:
            extraction = extract_with_gemini(messages, settings)
            engine = f"gemini ({settings.gemini_model or 'unset'})"
        except AIUnavailable as exc:
            notice = f"{exc} Falling back to the built-in rule-based extractor."
            logger.info("Falling back to rules: %s", exc)

    if extraction is None:
        extraction = rules.extract_commitments(messages)

    # A model that ignored the "don't invent dates" rule cannot do damage here:
    # every date is recomputed from the quoted wording by app.dates.
    return ExtractionReport(
        commitments=resolve(extraction, messages),
        messages=messages,
        engine=engine,
        notice=notice,
    )
