"""Gemini extraction layer.

Isolated on purpose: the rest of the app talks to :func:`extract_with_gemini`
only, so swapping the provider or the model touches this file alone.

Two invariants this layer enforces:

* the model never does date arithmetic — it copies the deadline wording verbatim
  and :mod:`app.dates` resolves it;
* the model never invents a deadline — no wording in the message means ``null``.
"""

from __future__ import annotations

import json
import logging

from app.config import Settings
from app.models import ExtractionResult, Message
from app.parsing import render_conversation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You extract COMMITMENTS from a business conversation.

A commitment is a statement in which a participant takes on an obligation to do
something: send a document, deliver a calculation, fix a bug, call back, pay.

Rules — follow all of them:
1. Extract only explicit commitments. Questions, opinions, plans without an
   obligation, and hedged statements ("I'll try", "maybe", "постараюсь") are NOT
   commitments.
2. `source_quote` must be copied verbatim from the conversation. Never paraphrase it.
3. `due_expression` must be the deadline wording copied verbatim from the same
   message ("завтра", "до пятницы", "25 сентября", "by Friday", "до конца недели").
   If the message names no deadline, return null.
4. NEVER compute, normalise or invent a calendar date. Do not return ISO dates
   unless that exact string appears in the message. Date arithmetic is done
   outside the model.
5. `message_index` must be the index printed in square brackets before the message.
6. `what` is one short sentence in the language of the conversation.
7. If the conversation contains no commitments, return an empty list.
"""

USER_TEMPLATE = """\
Conversation (each line is `[index] (timestamp) author: text`):

{conversation}

Extract every commitment as structured data.
"""


class AIUnavailable(RuntimeError):
    """Raised when Gemini cannot be reached, is out of quota, or answers with junk."""


def build_prompt(messages: list[Message]) -> str:
    return USER_TEMPLATE.format(conversation=render_conversation(messages))


def extract_with_gemini(messages: list[Message], settings: Settings) -> ExtractionResult:
    """Call Gemini and return validated structured output."""
    api_key = settings.gemini_api_key.strip()
    model = settings.gemini_model.strip()
    if not api_key:
        raise AIUnavailable("GEMINI_API_KEY is not configured.")
    if not model:
        raise AIUnavailable("GEMINI_MODEL is not configured.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on the deployment
        raise AIUnavailable(
            "The google-genai package is not installed; install it or set EXTRACTOR=rules."
        ) from exc

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(messages),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ExtractionResult,
                temperature=0.0,
                http_options=types.HttpOptions(timeout=int(settings.ai_timeout_seconds * 1000)),
            ),
        )
    except Exception as exc:
        # Never log the conversation or the key — only the error class and message.
        logger.warning("Gemini call failed: %s: %s", type(exc).__name__, exc)
        raise AIUnavailable(f"Gemini request failed: {type(exc).__name__}") from exc

    payload = getattr(response, "parsed", None)
    if isinstance(payload, ExtractionResult):
        return payload

    text = (getattr(response, "text", "") or "").strip()
    if not text:
        raise AIUnavailable("Gemini returned an empty response.")
    try:
        return ExtractionResult.model_validate(json.loads(text))
    except Exception as exc:
        logger.warning("Gemini returned unusable output: %s", type(exc).__name__)
        raise AIUnavailable("Gemini returned output that does not match the schema.") from exc
