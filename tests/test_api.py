from __future__ import annotations

import io

from fastapi.testclient import TestClient
from icalendar import Calendar


def test_healthz(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["extractor"] == "rules"


def test_index_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Extract promises" in response.text


def test_extract_renders_commitments(client: TestClient, conversation_ru: str) -> None:
    response = client.post(
        "/extract", data={"conversation": conversation_ru, "reference_date": "2026-09-14"}
    )
    assert response.status_code == 200
    assert "Needs confirmation" in response.text
    assert "2026-09-15" in response.text


def test_extract_requires_input(client: TestClient) -> None:
    response = client.post("/extract", data={"conversation": "   "})
    assert response.status_code == 400
    assert "Paste a conversation" in response.text


def test_extract_accepts_a_txt_upload(client: TestClient, conversation_ru: str) -> None:
    upload = io.BytesIO(conversation_ru.encode("utf-8"))
    response = client.post(
        "/extract",
        data={"reference_date": "2026-09-14"},
        files={"file": ("chat.txt", upload, "text/plain")},
    )
    assert response.status_code == 200
    assert "commitment(s)" in response.text


def test_non_utf8_upload_is_rejected(client: TestClient) -> None:
    upload = io.BytesIO("Отправлю завтра".encode("cp1251"))
    response = client.post("/extract", files={"file": ("chat.txt", upload, "text/plain")})
    assert response.status_code == 400


def test_api_extract(client: TestClient, conversation_ru: str) -> None:
    response = client.post(
        "/api/extract",
        json={"conversation": conversation_ru, "reference_date": "2026-09-14"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["messages"] == 20
    assert len(body["commitments"]) == 3
    assert [c["status"] for c in body["commitments"]].count("needs_confirmation") == 1


def test_api_extract_requires_conversation(client: TestClient) -> None:
    assert client.post("/api/extract", json={"conversation": ""}).status_code == 400


def _export_form() -> dict[str, list[str]]:
    """Two commitments as the confirmation form posts them: one dated, one not."""
    return {
        "id": ["c0", "c1"],
        "speaker": ["Сергей", "Сергей"],
        "recipient": ["Анна", "Анна"],
        "what": ["Отправить договор", "Исправить отчёт"],
        "source_quote": ["Отправлю договор завтра.", "Исправим отчёт."],
        "due_expression": ["завтра", ""],
        "anchor": ["2026-09-14T10:07:00", ""],
        "due_date": ["2026-09-15", ""],
        "due_time": ["18:00", ""],
        "include": ["c0", "c1"],
    }


def test_export_ics(client: TestClient) -> None:
    response = client.post("/export.ics", data=_export_form())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "promises.ics" in response.headers["content-disposition"]

    cal = Calendar.from_ical(response.content)
    events = cal.walk("VEVENT")
    assert len(events) == 1  # the undated one is left out
    assert "Отправить договор" in str(events[0]["summary"])


def test_export_honours_a_date_typed_by_the_user(client: TestClient) -> None:
    form = _export_form()
    form["due_date"] = ["2026-09-15", "2026-10-01"]
    cal = Calendar.from_ical(client.post("/export.ics", data=form).content)
    assert len(cal.walk("VEVENT")) == 2


def test_export_without_selection_is_rejected(client: TestClient) -> None:
    form = _export_form()
    form.pop("include")
    assert client.post("/export.ics", data=form).status_code == 400


def test_export_of_only_undated_commitments_is_rejected(client: TestClient) -> None:
    form = {
        "id": ["c1"],
        "speaker": ["S"],
        "recipient": [""],
        "what": ["Fix"],
        "source_quote": ["q"],
        "due_expression": [""],
        "anchor": [""],
        "due_date": [""],
        "due_time": [""],
        "include": ["c1"],
    }
    assert client.post("/export.ics", data=form).status_code == 400
