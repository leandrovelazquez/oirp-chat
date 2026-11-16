"""
FastAPI web server wrapping OIRPAgent.

Exposes a tiny HTTP API plus a single-page chat UI:

  GET  /                  → static/index.html (the chat page)
  POST /api/chat          → {"message": "..."} → {"text": "...", "confidence": "...", "trace": [...]}
  POST /api/chat/stream   → the same answer, preceded by progress lines (NDJSON)
  POST /api/reset        → clears the current session's conversation history
  GET  /api/info          → semantic layer summary (KPIs, record counts)

Per-session state is keyed by a `session_id` cookie. For this local-dev
demo we keep agents in a process-memory dict; in production you'd back
this with Redis or rebuild the agent per request and persist history
externally. Each session keeps its own conversation history but shares
the same loaded semantic layer (which is read-only and expensive to load).

Run it with:
    uvicorn oirp_agent.web:app --reload
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import threading
from pathlib import Path
from typing import Any

# Load .env if present, so `uvicorn oirp_agent.web:app` Just Works without
# the user having to remember to `export` first. Inline rather than depending
# on python-dotenv.
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _value = _line.partition("=")
        os.environ.setdefault(_key.strip(), _value.strip().strip('"').strip("'"))

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import DEFAULT_EFFORT, DEFAULT_MODEL, OIRPAgent, SemanticLayer


# ---------- Paths (resolved relative to the project root) ----------

# web.py lives at <project>/src/oirp_agent/web.py
# We want <project>/semantic_layer and <project>/static
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_LAYER_DIR = Path(
    os.environ.get("OIRP_SEMANTIC_LAYER_DIR", _PROJECT_ROOT / "semantic_layer")
)
STATIC_DIR = Path(os.environ.get("OIRP_STATIC_DIR", _PROJECT_ROOT / "static"))
MODEL = os.environ.get("OIRP_MODEL", DEFAULT_MODEL)
# low | medium | high | xhigh | max, or "none" to send no effort (older models).
EFFORT = os.environ.get("OIRP_EFFORT", DEFAULT_EFFORT or "none")
EFFORT = None if EFFORT.lower() == "none" else EFFORT.lower()

BASE_PROMPT_PATH = SEMANTIC_LAYER_DIR / "base_prompt.md"
KPI_DIR = SEMANTIC_LAYER_DIR / "kpis"
WAREHOUSE_DIR = SEMANTIC_LAYER_DIR / "warehouse"


# ---------- Shared semantic layer (loaded once at startup) ----------

# The published KPI files, the warehouse cube models, the synthetic warehouse
# connection and the assembled system prompt are loaded once and shared by
# reference. Each session gets its own OIRPAgent only for its own history.

_LAYER: SemanticLayer | None = None


def _ensure_semantic_layer_loaded() -> SemanticLayer:
    global _LAYER
    if _LAYER is None:
        _LAYER = SemanticLayer.load(KPI_DIR, BASE_PROMPT_PATH, WAREHOUSE_DIR)
    return _LAYER


# ---------- Per-session agent registry ----------

_SESSIONS: dict[str, OIRPAgent] = {}
SESSION_COOKIE = "oirp_session"


def _get_or_create_agent(session_id: str) -> OIRPAgent:
    """Return the agent for `session_id`, creating one if needed."""
    if session_id not in _SESSIONS:
        agent = OIRPAgent(
            semantic_layer_dir=KPI_DIR,
            base_prompt_path=BASE_PROMPT_PATH,
            model=MODEL,
            effort=EFFORT,
            layer=_ensure_semantic_layer_loaded(),
        )
        _SESSIONS[session_id] = agent
    return _SESSIONS[session_id]


# ---------- API request/response shapes ----------


class ChatRequest(BaseModel):
    message: str


class ToolCallSummary(BaseModel):
    name: str
    summary: str
    detail: str | None = None   # e.g. the SQL a query_metric call compiled to


class ResultTable(BaseModel):
    """The numbers a tool returned, as the page draws them (never from `text`)."""
    kind: str                   # "published" or "synthetic"
    title: str
    subtitle: str = ""
    columns: list[dict[str, Any]]   # {"name": str, "numeric": bool}
    rows: list[list[str]]       # display strings
    notes: list[str] = []
    data_as_of: str | None = None
    stale: bool = False
    preliminary: bool = False           # some row's numbers can still change
    row_preliminary: list[bool] = []    # which rows (empty when none are)
    chart: dict[str, Any] | None = None # line / bar / funnel, drawn from the same rows (numbers.chart_spec)


class ChatResponse(BaseModel):
    text: str
    confidence: str
    sources: list[str]          # "published" and/or "synthetic"
    trace: list[ToolCallSummary]
    tables: list[ResultTable] = []
    numbers_checked: int = 0    # numbers in `text` matched against tool results
    unverified: list[str] = []  # numbers no tool result supports (after one rewrite)
    number_retries: int = 0
    could_not_answer: str | None = None   # no_data | person | limit | unclear | unverified
    suggestions: list[str] = []           # questions it can answer instead
    follow_ups: list[str] = []            # next questions, worked out from the query


# ---------- App ----------

app = FastAPI(title="OIRP-chat", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    # Sanity-check the semantic layer at boot so we fail fast and loudly
    # if something's misconfigured, rather than per-request.
    _ensure_semantic_layer_loaded()
    # Don't pre-build a default agent — agents need an API key, and the user
    # may not have set one yet. Surface that error on first /api/chat instead.


@app.get("/api/info")
def info() -> dict[str, Any]:
    layer = _ensure_semantic_layer_loaded()
    cubes = layer.engine.describe()["cubes"] if layer.engine else []
    return {
        "kpi_count": len(layer.documents),
        "kpis": [
            {
                "kpi_id": d.kpi_id,
                "domain": d.domain,
                "status": d.status,
                "record_count": sum(len(b) for b in d.json_blocks),
            }
            for d in layer.documents
        ],
        "cube_count": len(cubes),
        "cubes": [
            {"cube": c["cube"], "data_as_of": c.get("data_as_of"), "stale": c.get("stale")}
            for c in cubes
        ],
        "model": MODEL,
        "effort": EFFORT,
        "active_sessions": len(_SESSIONS),
    }


def _session(request: Request) -> tuple[str, bool]:
    """The caller's session id, and whether it is new (needs a cookie)."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        return session_id, False
    return secrets.token_urlsafe(16), True


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,  # 24h
    )


def _error_body(e: Exception) -> dict[str, str]:
    """SDK / API errors, surfaced cleanly to the browser."""
    return {
        "error": type(e).__name__,
        "detail": str(e),
        "hint": (
            "If this says 'authentication', set ANTHROPIC_API_KEY in "
            "the terminal where you ran uvicorn and restart."
        ),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, response: Response) -> ChatResponse:
    session_id, new = _session(request)
    if new:
        _set_session_cookie(response, session_id)
    agent = _get_or_create_agent(session_id)
    try:
        result = agent.chat(req.message)
    except Exception as e:
        return JSONResponse(status_code=500, content=_error_body(e))
    return _to_response(result)


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """The same turn as /api/chat, reported as it happens.

    The body is newline-delimited JSON: zero or more
    `{"event": "progress", "step": ...}` lines (see OIRPAgent.chat), then one
    `{"event": "answer", ...ChatResponse}` or `{"event": "error", ...}` line.
    The answer's text arrives whole, after the number check, never in pieces.
    """
    session_id, new = _session(request)
    events: queue.Queue = queue.Queue()
    done = object()

    def work() -> None:
        try:
            agent = _get_or_create_agent(session_id)
            result = agent.chat(req.message, on_progress=lambda e: events.put({"event": "progress", **e}))
            events.put({"event": "answer", **_to_response(result).model_dump()})
        except Exception as e:  # noqa: BLE001 - reported to the page
            events.put({"event": "error", **_error_body(e)})
        finally:
            events.put(done)

    threading.Thread(target=work, daemon=True).start()

    def lines():
        while (item := events.get()) is not done:
            yield json.dumps(item, default=str) + "\n"

    # No-store and no proxy buffering, so each line reaches the page as it's written.
    response = StreamingResponse(lines(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    if new:
        _set_session_cookie(response, session_id)
    return response


def _to_response(result) -> ChatResponse:
    return ChatResponse(
        text=result.text,
        confidence=result.confidence.value,
        sources=result.trace.sources,
        trace=[
            ToolCallSummary(name=c.name, summary=c.result_summary, detail=c.detail)
            for c in result.trace.calls
        ],
        tables=[ResultTable(**{**t, "data_as_of": str(t["data_as_of"]) if t.get("data_as_of") else None})
                for t in result.tables],
        numbers_checked=result.numbers_checked,
        unverified=result.unverified,
        number_retries=result.number_retries,
        could_not_answer=result.could_not_answer,
        suggestions=result.suggestions,
        follow_ups=result.follow_ups,
    )


@app.post("/api/reset")
def reset(request: Request) -> dict[str, str]:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id and session_id in _SESSIONS:
        _SESSIONS[session_id].reset()
        return {"status": "reset"}
    return {"status": "no-session"}


# ---------- Static page mount ----------
#
# Mount LAST so the API routes above take precedence. The HTML page lives at
# /static/index.html; we also serve it directly at "/" for convenience.

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return JSONResponse(
            status_code=500,
            content={
                "error": "missing static/index.html",
                "expected_path": str(index),
            },
        )
    return FileResponse(index)


@app.get("/oirp")
def oirp_page() -> FileResponse:
    """The "What would you like to know?" page: one question box, answers as cards.

    Concept demo intended for OIRP-facing presentations. Uses the same
    /api/chat backend as the dev page at /. Watermarked as an unaffiliated
    portfolio project — not endorsed by Carleton or its OIRP. `?q=` asks a
    question on load, so a question can be shared as a link.
    """
    page = STATIC_DIR / "oirp.html"
    if not page.exists():
        return JSONResponse(
            status_code=500,
            content={
                "error": "missing static/oirp.html",
                "expected_path": str(page),
            },
        )
    return FileResponse(page)
