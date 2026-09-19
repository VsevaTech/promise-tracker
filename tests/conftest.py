from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(autouse=True)
def _no_real_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test suite must never reach a real AI provider."""
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "EXTRACTOR"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(gemini_api_key="", gemini_model="", extractor="rules")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def conversation_ru() -> str:
    return (EXAMPLES / "conversation_ru.txt").read_text(encoding="utf-8")


@pytest.fixture
def conversation_en() -> str:
    return (EXAMPLES / "conversation_en.txt").read_text(encoding="utf-8")
