"""Gemini is always mocked: CI must never need an API key."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.models import ExtractedCommitment, ExtractionResult, Message
from app.services import ai
from app.services.ai import AIUnavailable, build_prompt, extract_with_gemini

MESSAGES = [
    Message(index=0, author="Anna", text="Когда договор?"),
    Message(index=1, author="Sergey", text="Отправлю договор завтра."),
]

PAYLOAD = ExtractionResult(
    commitments=[
        ExtractedCommitment(
            speaker="Sergey",
            recipient="Anna",
            what="Отправить договор",
            due_expression="завтра",
            source_quote="Отправлю договор завтра.",
            message_index=1,
        )
    ]
)


class _FakeModels:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def _install_fake_sdk(monkeypatch: pytest.MonkeyPatch, models: _FakeModels) -> None:
    fake_client = SimpleNamespace(models=models)
    monkeypatch.setitem(
        __import__("sys").modules,
        "google",
        SimpleNamespace(genai=SimpleNamespace(Client=lambda api_key: fake_client)),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "google.genai",
        SimpleNamespace(
            Client=lambda api_key: fake_client,
            types=SimpleNamespace(
                GenerateContentConfig=lambda **kw: kw,
                HttpOptions=lambda **kw: kw,
            ),
        ),
    )


@pytest.fixture
def ai_settings() -> Settings:
    return Settings(gemini_api_key="test-key", gemini_model="gemini-test", extractor="gemini")


def test_uses_parsed_structured_output(monkeypatch: pytest.MonkeyPatch, ai_settings) -> None:
    models = _FakeModels(response=SimpleNamespace(parsed=PAYLOAD, text=""))
    _install_fake_sdk(monkeypatch, models)
    result = extract_with_gemini(MESSAGES, ai_settings)
    assert result.commitments[0].due_expression == "завтра"
    assert models.calls[0]["model"] == "gemini-test"


def test_falls_back_to_raw_json(monkeypatch: pytest.MonkeyPatch, ai_settings) -> None:
    raw = json.dumps(PAYLOAD.model_dump(mode="json"), ensure_ascii=False)
    _install_fake_sdk(monkeypatch, _FakeModels(response=SimpleNamespace(parsed=None, text=raw)))
    assert extract_with_gemini(MESSAGES, ai_settings).commitments[0].speaker == "Sergey"


def test_quota_error_becomes_ai_unavailable(monkeypatch: pytest.MonkeyPatch, ai_settings) -> None:
    _install_fake_sdk(monkeypatch, _FakeModels(error=RuntimeError("429 RESOURCE_EXHAUSTED")))
    with pytest.raises(AIUnavailable):
        extract_with_gemini(MESSAGES, ai_settings)


def test_garbage_output_becomes_ai_unavailable(
    monkeypatch: pytest.MonkeyPatch, ai_settings
) -> None:
    _install_fake_sdk(
        monkeypatch, _FakeModels(response=SimpleNamespace(parsed=None, text="not json"))
    )
    with pytest.raises(AIUnavailable):
        extract_with_gemini(MESSAGES, ai_settings)


def test_missing_key_or_model_is_reported_without_calling_out() -> None:
    with pytest.raises(AIUnavailable, match="GEMINI_API_KEY"):
        extract_with_gemini(MESSAGES, Settings(gemini_api_key="", gemini_model="m"))
    with pytest.raises(AIUnavailable, match="GEMINI_MODEL"):
        extract_with_gemini(MESSAGES, Settings(gemini_api_key="k", gemini_model=""))


def test_prompt_carries_indexes_and_timestamps() -> None:
    prompt = build_prompt(MESSAGES)
    assert "[1]" in prompt and "Sergey" in prompt


def test_prompt_forbids_date_arithmetic() -> None:
    assert "NEVER compute" in ai.SYSTEM_PROMPT


def test_schema_cannot_carry_a_computed_date() -> None:
    """Structural guarantee: the model has nowhere to put an invented date."""
    fields = set(ExtractedCommitment.model_fields)
    assert "due_expression" in fields
    assert not fields & {"due_date", "deadline", "date", "due_at"}
