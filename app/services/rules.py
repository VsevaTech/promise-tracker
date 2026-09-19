"""Rule-based commitment extraction.

This is the zero-dependency fallback: it runs when no Gemini key is configured,
when EXTRACTOR=rules, and whenever the AI call fails. Recall is lower than the
model's, but the app stays useful (and testable) without any external service.
"""

from __future__ import annotations

import re

from app.dates import find_due_expression
from app.models import ExtractedCommitment, ExtractionResult, Message

# First-person promise verbs. Grouped only for readability.
_PROMISE_STEMS_RU = (
    r"отправл|вышл|пришл|направл|подготов|сдела|додела|дораб|исправ|поправ|почин|"
    r"посчита|рассчита|предостав|верн|провер|уточн|выставл|оплат|настро|запуст|"
    r"выкат|закро|опиш|отпиш|согласу|подпиш|перезвон|созвон|обнов|скин|завед|добав|"
    r"переда|покаж|расскаж|ответ|орган"
)
# Verb endings only, so that nouns like "проверка" or "отправление" do not match.
_VERB_ENDINGS_RU = r"(?:у|ю|ем|ём|им|усь|юсь|емся|ёмся|имся|ешь|ишь|ите|ю сь)"
_PROMISE_RU = re.compile(
    rf"\b(?:{_PROMISE_STEMS_RU}){_VERB_ENDINGS_RU}\b|\b(?:дам|дадим|сделаем|пришлём|пришлем)\b",
    flags=re.IGNORECASE,
)
_PROMISE_EN = re.compile(
    r"\b(?:i|we)\s*(?:'|’)?(?:ll|will)\b|\b(?:i|we)\s+(?:am|are)\s+going\s+to\b"
    r"|\bwill\s+(?:send|share|deliver|fix|prepare|get\s+back|provide|update|call)\b",
    flags=re.IGNORECASE,
)

# Wording that makes a sentence something other than a commitment.
_HEDGES = re.compile(
    r"\b(?:постара\w*|попробу\w*|возможно|наверное|может быть|если получится|"
    r"по возможности|не обеща\w*|не гарантиру\w*|"
    r"maybe|probably|might|hopefully|if possible|try to|no promises)\b",
    flags=re.IGNORECASE,
)
_QUESTION_WORDS = re.compile(
    r"\b(?:когда|можешь|можете|сможешь|сможете|подскажи\w*|when|can you|could you|will you)\b",
    flags=re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


def _is_commitment(sentence: str) -> bool:
    if "?" in sentence or _QUESTION_WORDS.search(sentence):
        return False
    if _HEDGES.search(sentence):
        return False
    return bool(_PROMISE_RU.search(sentence) or _PROMISE_EN.search(sentence))


def _summarize(sentence: str) -> str:
    cleaned = re.sub(r"\s+", " ", sentence).strip(" .,;:!—-")
    return cleaned[:200]


def _recipient_for(messages: list[Message], message: Message) -> str | None:
    """The person being answered: the nearest earlier author who is someone else."""
    for earlier in reversed(messages[: message.index]):
        if earlier.author and earlier.author != message.author:
            return earlier.author
    return None


def extract_commitments(messages: list[Message]) -> ExtractionResult:
    found: list[ExtractedCommitment] = []
    for message in messages:
        for sentence in _SENTENCE_SPLIT.split(message.text):
            sentence = sentence.strip()
            if len(sentence) < 8 or not _is_commitment(sentence):
                continue
            found.append(
                ExtractedCommitment(
                    speaker=message.author,
                    recipient=_recipient_for(messages, message),
                    what=_summarize(sentence),
                    due_expression=find_due_expression(sentence),
                    source_quote=sentence[:400],
                    message_index=message.index,
                )
            )
    return ExtractionResult(commitments=found)
