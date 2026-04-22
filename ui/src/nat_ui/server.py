"""FastAPI backend for the browser chat UI with live progress streaming.

Endpoints
---------
- ``POST /api/chat`` — enqueue a user query; returns ``{job_id}``.
- ``GET  /api/chat/{job_id}`` — poll the job (status + last-known pill states +
  buffered events). Fallback for browsers/clients that can't use SSE.
- ``GET  /api/chat/{job_id}/stream`` — Server-Sent Events. Replays the full
  event history on connect, then pushes new events until the job terminates.
- ``POST /api/events/{job_id}`` — progress ingestion endpoint called by the
  e2e orchestrator, each extractor, and the reporter. Events are broadcast
  to every active SSE subscriber and stored in the job buffer for replay.
- ``GET  /api/reports/{name}`` — read a generated markdown report.

Run modes (``NAT_UI_STUB`` env var)
-----------------------------------
- STUB (default ``1``): the pipeline is faked. A background coroutine emits
  events on the same event bus with realistic timings so the frontend render
  path can be exercised without any agents running.
- LIVE (``0``): the envelope is forwarded to the e2e A2A endpoint along with
  ``event_url`` pointing back at this server; tools POST their own progress.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

JobStatus = Literal["pending", "done", "error"]
AgentStatus = Literal["pending", "working", "done", "error"]

# Fixed agent list rendered in the UI. Order matches the pipeline flow:
# query-generator → 7 parallel collectors → reporter.
AGENTS: list[tuple[str, str]] = [
    ("query-generator", "Query Generator"),
    ("arcalive", "ArcaLive"),
    ("arxiv", "arXiv"),
    ("benchmark", "Benchmark"),
    ("geeknews", "GeekNews"),
    ("lobsters", "Lobsters"),
    ("openai", "OpenAI Blog"),
    ("reddit", "Reddit"),
    ("reporter", "Reporter"),
]

COLLECTOR_IDS: list[str] = [
    "arcalive", "arxiv", "benchmark", "geeknews",
    "lobsters", "openai", "reddit",
]

STUB_AGENT_MAX_SECONDS = float(os.environ.get("NAT_UI_STUB_AGENT_MAX", "10"))
QUERY_GEN_VISUAL_DELAY_SECONDS = float(os.environ.get("NAT_UI_QUERY_GEN_DELAY", "5"))


def _initial_agent_state() -> dict[str, "AgentStatus"]:
    """Phase-1 initial state: query-generator running, everything else pending."""
    state: dict[str, AgentStatus] = {aid: "pending" for aid, _ in AGENTS}
    state["query-generator"] = "working"
    return state

UI_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = UI_ROOT / "static"
DEFAULT_REPORTS_DIR = UI_ROOT / "reports"

REPORTS_DIR = Path(os.environ.get("NAT_UI_REPORTS_DIR", DEFAULT_REPORTS_DIR)).resolve()
E2E_URL = os.environ.get("NAT_UI_E2E_URL", "http://localhost:10000")
STUB_MODE = os.environ.get("NAT_UI_STUB", "1") == "1"
E2E_TIMEOUT_SECONDS = float(os.environ.get("NAT_UI_E2E_TIMEOUT", "600"))

# Base URL other containers use to reach this UI backend for event POSTs. In
# docker-compose this is ``http://ui:8080``; bare local runs default to the
# loopback host+port. Callers must reach us at <base>/api/events/<job_id>.
_DEFAULT_PUBLIC = f"http://{os.environ.get('NAT_UI_HOST', '127.0.0.1')}:{os.environ.get('NAT_UI_PORT', '8080')}"
PUBLIC_EVENT_BASE = os.environ.get("NAT_UI_PUBLIC_EVENT_BASE", _DEFAULT_PUBLIC).rstrip("/")


@dataclass
class Job:
    """In-memory state for a single UI chat submission.

    ``events`` is the authoritative progress log — appended to by the POST
    ingestion endpoint and replayed in order to late SSE subscribers. Every
    append is also fan-out to ``subscribers`` (one queue per live SSE
    connection) so streaming readers wake up without polling.

    ``agents`` is a derived view kept in sync so the fallback polling endpoint
    can still render pill statuses for clients that didn't open SSE.
    """

    id: str
    query: str
    status: JobStatus = "pending"
    report_name: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    agents: dict[str, AgentStatus] = field(default_factory=_initial_agent_state)
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)


JOBS: dict[str, Job] = {}


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    job_id: str


class AgentState(BaseModel):
    id: str
    label: str
    status: AgentStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    agents: list[AgentState]
    report_name: str | None = None
    error: str | None = None
    events: list[dict[str, Any]] = []


app = FastAPI(title="AI Product Feedback Aggregator — Chat UI")


@app.on_event("startup")
async def _ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", text.strip(), flags=re.UNICODE).strip("-")
    return slug[:40] or "query"


def _new_report_name(query: str) -> str:
    return f"{int(time.time())}-{_slugify(query)}.report.md"


async def _a2a_send(url: str, message: str, timeout: float) -> str:
    """A2A v0.3 message/send over HTTP. Matches agents/e2e/src/nat_e2e/register.py."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": message}],
            },
        },
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    result = data.get("result", {})
    artifacts = result.get("artifacts", [])
    if artifacts:
        parts = artifacts[0].get("parts", [])
        return parts[0].get("text", "") if parts else ""
    parts = result.get("parts", [])
    return parts[0].get("text", "") if parts else ""


def _stub_report(query: str) -> str:
    return (
        f"# Briefing preview: {query}\n\n"
        "> This is a placeholder generated by the UI in **STUB mode**.\n"
        "> The real briefing will appear here once the live pipeline is wired in.\n\n"
        "## Summary\n\n"
        f"- Topic: **{query}**\n"
        "- Source: stubbed\n"
        "- Generated: just now\n\n"
        "## Notes\n\n"
        "In live mode, the briefing will combine official benchmarks, papers, "
        "and community reactions into a single structured view rendered below "
        "the user message.\n"
    )


def _publish_event(job: Job, event: dict[str, Any]) -> None:
    """Append an event to the job log and wake every live SSE subscriber.

    Also mutates ``job.agents`` so the polling fallback reflects the same
    pill transitions. ``agent``-scoped events flip that pill's status; phase
    transitions without an agent are ignored here (SSE consumers render them
    via phase headers).
    """
    job.events.append(event)
    agent = event.get("agent")
    etype = event.get("type")
    if agent and agent in job.agents and etype in {"start", "progress", "complete", "error"}:
        if etype in {"start", "progress"}:
            job.agents[agent] = "working"
        elif etype == "complete":
            job.agents[agent] = "done"
        elif etype == "error":
            job.agents[agent] = "error"
    for q in list(job.subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _make_event(
    *,
    agent: str | None,
    event_type: str,
    phase: str | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an event dict in the shared wire-schema shape.

    Mirrors ``ari_core.events.build_event_payload`` but without requiring the
    contextvar — the UI backend manufactures events locally (job-end, STUB
    mode, ingestion pass-through) where contextvars don't apply.
    """
    return {
        "ts": time.time(),
        "agent": agent,
        "phase": phase,
        "type": event_type,
        "message": message,
        "data": data or {},
    }


async def _run_stub(job: Job) -> str:
    """Stub run: publish fake events on the same bus with realistic timings."""
    _publish_event(
        job,
        _make_event(
            agent="query-generator",
            event_type="start",
            phase="plan",
            message="Extracting product names…",
        ),
    )
    await asyncio.sleep(QUERY_GEN_VISUAL_DELAY_SECONDS)
    _publish_event(
        job,
        _make_event(
            agent="query-generator",
            event_type="complete",
            phase="plan",
            message="1 product identified",
            data={"products": [job.query]},
        ),
    )

    async def _stub_collector(aid: str) -> None:
        _publish_event(
            job,
            _make_event(
                agent=aid,
                event_type="start",
                phase="collect",
                message=f"{aid}: scraping…",
            ),
        )
        scraped = random.randint(3, 25)
        await asyncio.sleep(random.uniform(0.5, STUB_AGENT_MAX_SECONDS / 2))
        _publish_event(
            job,
            _make_event(
                agent=aid,
                event_type="progress",
                phase="collect",
                message=f"{aid}: {scraped} items scraped, validating…",
                data={"scraped": scraped},
            ),
        )
        await asyncio.sleep(random.uniform(0.5, STUB_AGENT_MAX_SECONDS / 2))
        validated = random.randint(0, scraped)
        _publish_event(
            job,
            _make_event(
                agent=aid,
                event_type="complete",
                phase="collect",
                message=f"{aid}: {validated}/{scraped} validated",
                data={"scraped": scraped, "validated": validated},
            ),
        )

    await asyncio.gather(*[_stub_collector(aid) for aid in COLLECTOR_IDS])

    _publish_event(
        job,
        _make_event(
            agent="reporter",
            event_type="start",
            phase="report",
            message="Synthesizing briefing…",
        ),
    )
    await asyncio.sleep(random.uniform(1.0, STUB_AGENT_MAX_SECONDS))
    _publish_event(
        job,
        _make_event(
            agent="reporter",
            event_type="complete",
            phase="report",
            message="Briefing ready",
        ),
    )

    return _stub_report(job.query)


async def _run_live(job: Job) -> str:
    """Forward the query to e2e; tools POST their own events back."""
    work_dir = REPORTS_DIR / job.id
    work_dir.mkdir(parents=True, exist_ok=True)

    envelope = json.dumps(
        {
            "job_id": job.id,
            "work_dir": str(work_dir),
            "query": job.query,
            "event_url": f"{PUBLIC_EVENT_BASE}/api/events/{job.id}",
        },
        ensure_ascii=False,
    )
    markdown = await _a2a_send(E2E_URL, envelope, E2E_TIMEOUT_SECONDS)
    if not markdown.strip():
        raise RuntimeError("Empty response from e2e agent")
    # Force any unfinished pill to done — guards against missing complete events.
    for aid in job.agents:
        if job.agents[aid] in ("pending", "working"):
            job.agents[aid] = "done"
    return markdown


async def _run_job(job: Job) -> None:
    """Execute one job and emit a terminal ``job_end`` event for SSE closers."""
    try:
        markdown = await (_run_stub(job) if STUB_MODE else _run_live(job))
        report_name = _new_report_name(job.query)
        (REPORTS_DIR / report_name).write_text(markdown, encoding="utf-8")
        job.report_name = report_name
        job.status = "done"
        _publish_event(
            job,
            _make_event(
                agent=None,
                event_type="complete",
                message="Pipeline finished",
                data={"report_name": report_name},
            ),
        )
    except Exception as exc:
        for aid, status in job.agents.items():
            if status in ("pending", "working"):
                job.agents[aid] = "error"
        job.error = f"{type(exc).__name__}: {exc}"
        job.status = "error"
        _publish_event(
            job,
            _make_event(
                agent=None,
                event_type="error",
                message=job.error,
            ),
        )


@app.post("/api/chat", response_model=ChatResponse)
async def create_chat(req: ChatRequest) -> ChatResponse:
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is empty")
    job = Job(id=str(uuid.uuid4()), query=query)
    JOBS[job.id] = job
    asyncio.create_task(_run_job(job))
    return ChatResponse(job_id=job.id)


@app.get("/api/chat/{job_id}", response_model=JobStatusResponse)
async def get_chat(job_id: str) -> JobStatusResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    agents = [
        AgentState(id=aid, label=label, status=job.agents.get(aid, "working"))
        for aid, label in AGENTS
    ]
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        agents=agents,
        report_name=job.report_name,
        error=job.error,
        events=list(job.events),
    )


@app.post("/api/events/{job_id}", status_code=202)
async def post_event(job_id: str, request: Request) -> dict[str, str]:
    """Ingest a single progress event from a pipeline tool/agent.

    Returns 202 Accepted with a trivial body so the caller (which uses a 1s
    fire-and-forget timeout) can close the connection immediately. Unknown
    job_ids return 404 so mis-routed events fail loud on the emitter side.
    """
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="event must be a JSON object")
    _publish_event(job, payload)
    return {"status": "accepted"}


async def _sse_stream(job: Job) -> AsyncIterator[bytes]:
    """Yield SSE frames: replay buffered events, then stream live ones.

    A small ``asyncio.Queue`` is registered in ``job.subscribers`` so every
    ``_publish_event`` call wakes this generator. The stream ends when it
    sees a terminal event (``type=complete`` or ``type=error`` with no
    ``agent``) — these are emitted by ``_run_job`` on success/failure.
    """
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    job.subscribers.add(q)
    try:
        # Replay history first so a late subscriber catches up.
        for event in list(job.events):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
            if _is_terminal(event):
                return
        # If the job already finished before we subscribed, _is_terminal
        # above would have returned — otherwise wait for new events.
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # keep-alive comment, RFC spec-compliant
                yield b": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
            if _is_terminal(event):
                return
    finally:
        job.subscribers.discard(q)


def _is_terminal(event: dict[str, Any]) -> bool:
    """Terminal = pipeline-level complete/error event (no agent attached)."""
    return event.get("agent") is None and event.get("type") in {"complete", "error"}


@app.get("/api/chat/{job_id}/stream")
async def stream_chat(job_id: str) -> StreamingResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return StreamingResponse(
        _sse_stream(job),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx-style buffering if fronted
        },
    )


@app.get("/api/reports/{name}", response_class=PlainTextResponse)
async def get_report(name: str) -> PlainTextResponse:
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="invalid report name")
    path = (REPORTS_DIR / name).resolve()
    if REPORTS_DIR not in path.parents and path.parent != REPORTS_DIR:
        raise HTTPException(status_code=400, detail="invalid report path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="report not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/api/config")
async def get_config() -> dict:
    return {
        "stub_mode": STUB_MODE,
        "e2e_url": E2E_URL,
        "reports_dir": str(REPORTS_DIR),
        "public_event_base": PUBLIC_EVENT_BASE,
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    host = os.environ.get("NAT_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("NAT_UI_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
