"""HTTP API for the web UI: start a run, stream progress (SSE), fetch the report, answer questions."""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from revizorro import __version__
from revizorro.config import REPO_ROOT, load_settings, normalize_model_id
from revizorro.domain.criteria import ALL, INDIVIDUAL, SET
from revizorro.domain.models import DECISION_RU, KIND_RU, SEVERITY_RU, Report
from revizorro.ingestion import SUPPORTED
from revizorro.pipeline.orchestrator import run_review
from revizorro.reporting.renderer import render_html, render_markdown

WORK_DIR = Path(tempfile.gettempdir()) / "revizorro-api"
EXAMPLE = REPO_ROOT / "examples" / "requirements.md"


@dataclass
class Run:
    id: str
    source: Path
    filename: str
    model_default: str
    model_strong: str
    answers: dict[str, str] = field(default_factory=dict)
    status: str = "queued"  # queued | running | done | failed
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    report: Report | None = None
    markdown: str | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)

    def push(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.changed.set()


class AnswersIn(BaseModel):
    answers: dict[str, str]


app = FastAPI(title="Revizorro API", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
RUNS: dict[str, Run] = {}
TASKS: set[asyncio.Task[None]] = set()


async def _execute(run: Run) -> None:
    settings = load_settings()
    run.status = "running"
    run.push({"type": "run", "status": "running"})
    try:
        report = await run_review(
            run.source,
            settings,
            model_default=run.model_default,
            model_strong=run.model_strong,
            answers=run.answers or None,
            on_event=run.push,
        )
        run.report = report
        run.markdown = render_markdown(report)
        run.status = "done"
        run.push({"type": "run", "status": "done", "decision": report.verdict.decision})
    except Exception as e:  # surface any failure to the client instead of hanging the stream
        run.status, run.error = "failed", str(e)
        run.push({"type": "run", "status": "failed", "error": str(e)})


def _start(run: Run) -> Run:
    RUNS[run.id] = run
    task = asyncio.get_running_loop().create_task(_execute(run))
    TASKS.add(task)  # keep a reference so the task is not garbage-collected mid-run
    task.add_done_callback(TASKS.discard)
    return run


def _get(run_id: str) -> Run:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "Прогон не найден")
    return run


def _summary(run: Run) -> dict[str, Any]:
    return {
        "id": run.id,
        "filename": run.filename,
        "status": run.status,
        "error": run.error,
        "model_default": run.model_default,
        "model_strong": run.model_strong,
        "answers": run.answers,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = load_settings()
    try:
        default, strong = settings.resolve_models()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "version": __version__, "model_default": default, "model_strong": strong}


@app.post("/api/runs")
async def create_run(
    file: Annotated[UploadFile, File()],
    model: Annotated[str | None, Form()] = None,
    strong_model: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    suffix = Path(file.filename or "document.md").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(415, f"Формат {suffix} не поддерживается: {', '.join(sorted(SUPPORTED))}")
    default, strong = _models(model, strong_model)
    run_id = uuid.uuid4().hex[:12]
    folder = WORK_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / f"input{suffix}"
    source.write_bytes(await file.read())
    run = _start(Run(run_id, source, file.filename or source.name, default, strong))
    return _summary(run)


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """Russian labels for codes used in the report: one source of truth for the UI."""
    return {
        "criteria": {c.code: {"name": c.name, "source": c.source} for c in ALL.values()},
        "individual": list(INDIVIDUAL),
        "set": list(SET),
        "severity": SEVERITY_RU,
        "kind": KIND_RU,
        "decision": DECISION_RU,
        "example": EXAMPLE.is_file(),
    }


@app.post("/api/runs/example")
async def create_example_run(model: str | None = None, strong_model: str | None = None) -> dict[str, Any]:
    """Run the organisers' sample document shipped in examples/."""
    if not EXAMPLE.is_file():
        raise HTTPException(404, "Пример не найден: examples/requirements.md")
    default, strong = _models(model, strong_model)
    return _summary(_start(Run(uuid.uuid4().hex[:12], EXAMPLE, EXAMPLE.name, default, strong)))


def _models(model: str | None, strong_model: str | None) -> tuple[str, str]:
    default, strong = load_settings().resolve_models()
    if model:
        default = normalize_model_id(model)
        strong = normalize_model_id(strong_model) if strong_model else default
    return default, strong


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _summary(_get(run_id))


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> EventSourceResponse:
    run = _get(run_id)

    async def stream():
        sent = 0
        while True:
            while sent < len(run.events):
                yield {
                    "event": run.events[sent]["type"],
                    "data": json.dumps(run.events[sent], ensure_ascii=False),
                }
                sent += 1
            if run.status in ("done", "failed"):
                return
            run.changed.clear()
            try:
                await asyncio.wait_for(run.changed.wait(), timeout=15)
            except TimeoutError:
                yield {"event": "ping", "data": "{}"}

    return EventSourceResponse(stream())


@app.get("/api/runs/{run_id}/report")
def get_report(run_id: str) -> dict[str, Any]:
    run = _get(run_id)
    if run.report is None:
        raise HTTPException(409, f"Отчёт ещё не готов: {run.status}")
    return json.loads(run.report.model_dump_json())


@app.get("/api/runs/{run_id}/report.md", response_class=PlainTextResponse)
def get_report_md(run_id: str) -> str:
    run = _get(run_id)
    if run.markdown is None:
        raise HTTPException(409, f"Отчёт ещё не готов: {run.status}")
    return run.markdown


@app.get("/api/runs/{run_id}/report.html", response_class=HTMLResponse)
def get_report_html(run_id: str) -> str:
    run = _get(run_id)
    if run.report is None or run.markdown is None:
        raise HTTPException(409, f"Отчёт ещё не готов: {run.status}")
    return render_html(run.report, run.markdown)


@app.post("/api/runs/{run_id}/answers")
async def answer(run_id: str, body: AnswersIn) -> dict[str, Any]:
    """Start a follow-up run with answers; cached model calls make it fast."""
    prev = _get(run_id)
    if prev.report is None:
        raise HTTPException(409, "Сначала дождитесь завершения прогона")
    answers = {**prev.answers, **{k: v for k, v in body.answers.items() if v.strip()}}
    run = _start(
        Run(uuid.uuid4().hex[:12], prev.source, prev.filename, prev.model_default, prev.model_strong, answers)
    )
    return _summary(run)


_FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "dist"
if _FRONTEND.is_dir():

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        target = _FRONTEND / path
        return FileResponse(target if target.is_file() else _FRONTEND / "index.html")


def serve() -> None:
    """Entry point: `revizorro-api` (uvicorn on http://127.0.0.1:8000)."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
