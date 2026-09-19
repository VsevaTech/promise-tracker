"""FastAPI application: paste a conversation, confirm the promises, download .ics."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import get_settings
from app.extractor import extract
from app.ics import NothingToExport, render_ics
from app.web import commitments_from_form

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Promise Tracker", version=__version__)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "extractor": "gemini" if settings.gemini_enabled else "rules",
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "today": date.today().isoformat(),
            "ai_enabled": settings.gemini_enabled,
            "version": __version__,
        },
    )


async def _read_conversation(text: str, upload: UploadFile | None) -> str:
    settings = get_settings()
    if upload is not None and upload.filename:
        blob = await upload.read()
        if len(blob) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="The uploaded file is too large.")
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="The file must be UTF-8 encoded plain text."
            ) from exc
    return text or ""


def _reference(raw: str | None) -> datetime:
    if raw:
        try:
            return datetime.combine(date.fromisoformat(raw), datetime.min.time())
        except ValueError:
            pass
    return datetime.now()


@app.post("/extract", response_class=HTMLResponse)
async def extract_view(
    request: Request,
    conversation: str = Form(default=""),
    reference_date: str = Form(default=""),
    file: UploadFile | None = None,
) -> HTMLResponse:
    text = await _read_conversation(conversation, file)
    if not text.strip():
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"message": "Paste a conversation or upload a .txt file first."},
            status_code=400,
        )

    report = extract(text, reference=_reference(reference_date))
    return templates.TemplateResponse(request, "partials/commitments.html", {"report": report})


@app.post("/api/extract")
async def api_extract(payload: dict) -> JSONResponse:
    text = str(payload.get("conversation", ""))
    if not text.strip():
        raise HTTPException(status_code=400, detail="conversation is required")
    report = extract(text, reference=_reference(payload.get("reference_date")))
    return JSONResponse(
        {
            "engine": report.engine,
            "notice": report.notice,
            "messages": len(report.messages),
            "commitments": [c.model_dump(mode="json") for c in report.commitments],
        }
    )


@app.post("/export.ics")
async def export_ics(request: Request) -> Response:
    form = await request.form()
    grouped: dict[str, list[str]] = {}
    for key, value in form.multi_items():
        grouped.setdefault(key, []).append(str(value))

    commitments = commitments_from_form(grouped)
    if not commitments:
        raise HTTPException(status_code=400, detail="Select at least one commitment.")
    try:
        body = render_ics(commitments, get_settings())
    except NothingToExport as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="promises.ics"'},
    )
