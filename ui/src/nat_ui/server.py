"""FastAPI backend for the browser chat UI.

Exposes three endpoints:
- POST /api/chat              : enqueue a user query, returns job_id immediately.
- GET  /api/chat/{job_id}     : poll job status (pending / done / error).
- GET  /api/reports/{name}    : read a generated markdown report.

Two run modes, selected via the NAT_UI_STUB env var:
- STUB (default, NAT_UI_STUB=1): write a canned sample markdown after a short
  delay. Useful while the e2e agent is still being built.
- LIVE (NAT_UI_STUB=0): POST the query to the e2e A2A endpoint and save the
  returned markdown to REPORTS_DIR.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

JobStatus = Literal["pending", "done", "error"]
AgentStatus = Literal["pending", "working", "done", "error"]

# Phase 2 sources, each of which runs a collect → validate sub-pipeline.
SOURCES: list[tuple[str, str]] = [
    ("arcalive", "ArcaLive"),
    ("arxiv", "arXiv"),
    ("benchmark", "Benchmark"),
    ("geeknews", "GeekNews"),
    ("lobsters", "Lobsters"),
    ("openai", "OpenAI Blog"),
    ("reddit", "Reddit"),
]

# Sub-stages inside each source (order is meaningful — collect runs first).
STAGES: list[tuple[str, str]] = [
    ("collect", "collect"),
    ("validate", "validate"),
]

SOURCE_IDS: list[str] = [sid for sid, _ in SOURCES]


def _collector_pill_ids() -> list[tuple[str, str]]:
    """(pill_id, label) for every collect/validate pill under phase 2.

    Label is just the stage name ("collect"/"validate") — the source name is
    rendered by the frontend as the source card header, so we avoid duplicating
    it in the pill itself.
    """
    return [
        (f"{sid}-{stage_id}", stage_label)
        for sid, _ in SOURCES
        for stage_id, stage_label in STAGES
    ]


# Fixed agent list rendered in the UI. Order matches the pipeline flow:
# query-generator → 7 sources × (collect, validate) → reporter.
AGENTS: list[tuple[str, str]] = (
    [("query-generator", "Query Generator")]
    + _collector_pill_ids()
    + [("reporter", "Reporter")]
)

STUB_AGENT_MAX_SECONDS = float(os.environ.get("NAT_UI_STUB_AGENT_MAX", "10"))
# Query Generator is animated as a fixed visual delay — it never produces a
# *.md artifact; we just show a 5s "working" state before phase 2 begins.
QUERY_GEN_VISUAL_DELAY_SECONDS = float(os.environ.get("NAT_UI_QUERY_GEN_DELAY", "5"))


def _initial_agent_state() -> dict[str, "AgentStatus"]:
    """Phase-1 initial state: query-generator running, everything else pending."""
    state: dict[str, AgentStatus] = {aid: "pending" for aid, _ in AGENTS}
    state["query-generator"] = "working"
    return state

UI_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = UI_ROOT / "static"
REPO_ROOT = UI_ROOT.parent
DEFAULT_REPORTS_DIR = UI_ROOT / "reports"
DEFAULT_RUNS_ROOT = REPO_ROOT / "runs"

REPORTS_DIR = Path(os.environ.get("NAT_UI_REPORTS_DIR", DEFAULT_REPORTS_DIR)).resolve()
RUNS_ROOT = Path(os.environ.get("ARI_RUNS_ROOT", DEFAULT_RUNS_ROOT)).resolve()
E2E_URL = os.environ.get("NAT_UI_E2E_URL", "http://localhost:10000")
STUB_MODE = os.environ.get("NAT_UI_STUB", "1") == "1"
E2E_TIMEOUT_SECONDS = float(os.environ.get("NAT_UI_E2E_TIMEOUT", "600"))

# Backend run_id pattern: YYYYMMDD-HHMMSS-xxxxxxxx (see ari_core.new_run_id).
_RUN_ID_RE = re.compile(r"\b(\d{8}-\d{6}-[0-9a-f]{8})\b")


def _product_slug(name: str) -> str:
    """Mirror ari_core.slugify_product — lowercase + non-alnum → dash."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "product"


def _load_run_products(run_id: str) -> list[str]:
    """Read ``runs/{run_id}/query.json`` and return ``products``."""
    try:
        data = json.loads(
            (RUNS_ROOT / run_id / "query.json").read_text(encoding="utf-8")
        )
        products = data.get("products", [])
        if isinstance(products, list):
            return [str(p) for p in products]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _concat_run_reports(run_id: str) -> str:
    """Concatenate ``runs/{run_id}/report_*.md`` in product order."""
    root = RUNS_ROOT / run_id
    products = _load_run_products(run_id)
    parts: list[str] = []
    seen: set[Path] = set()
    for product in products:
        p = root / f"report_{_product_slug(product)}.md"
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8").rstrip() + "\n")
            seen.add(p)
    for p in sorted(root.glob("report_*.md")):
        if p in seen:
            continue
        parts.append(p.read_text(encoding="utf-8").rstrip() + "\n")
    return "\n---\n\n".join(parts)


@dataclass
class Job:
    id: str
    query: str
    status: JobStatus = "pending"
    report_name: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    agents: dict[str, AgentStatus] = field(default_factory=_initial_agent_state)
    run_id: str | None = None


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


async def _run_stub(job: Job) -> str:
    """Purely visual run: phase 1 (5s) → phase 2 (per-source collect→validate) → phase 3."""
    # Phase 1 — query-generator fixed visual delay.
    await asyncio.sleep(QUERY_GEN_VISUAL_DELAY_SECONDS)
    job.agents["query-generator"] = "done"

    # Phase 2 — each source runs collect → validate sequentially; all 7 sources
    # start their collect stages in parallel.
    for sid in SOURCE_IDS:
        job.agents[f"{sid}-collect"] = "working"

    async def _stub_source(sid: str) -> None:
        collect_key = f"{sid}-collect"
        validate_key = f"{sid}-validate"
        await asyncio.sleep(random.uniform(0.0, STUB_AGENT_MAX_SECONDS))
        job.agents[collect_key] = "done"
        job.agents[validate_key] = "working"
        await asyncio.sleep(random.uniform(0.0, STUB_AGENT_MAX_SECONDS))
        job.agents[validate_key] = "done"

    await asyncio.gather(*[_stub_source(sid) for sid in SOURCE_IDS])

    # Phase 3 — reporter starts only after every source finishes validate.
    job.agents["reporter"] = "working"
    await asyncio.sleep(random.uniform(0.0, STUB_AGENT_MAX_SECONDS))
    job.agents["reporter"] = "done"

    return _stub_report(job.query)


async def _detect_run_id(since: float, deadline: float) -> str | None:
    """Watch RUNS_ROOT for a new run_id directory created after ``since``.

    The e2e ``plan_query`` tool allocates run_id internally and writes
    ``runs/{run_id}/query.json`` as its first side effect; we pick up the
    newest ``YYYYMMDD-HHMMSS-xxxxxxxx`` directory whose mtime is >= ``since``.
    """
    while time.time() < deadline:
        if RUNS_ROOT.exists():
            best: tuple[float, str] | None = None
            for p in RUNS_ROOT.iterdir():
                if not p.is_dir() or not _RUN_ID_RE.fullmatch(p.name):
                    continue
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                if mtime < since - 1.0:
                    continue
                if best is None or mtime > best[0]:
                    best = (mtime, p.name)
            if best is not None:
                return best[1]
        await asyncio.sleep(0.5)
    return None


def _update_agents_from_run(job: Job, run_id: str) -> None:
    """Drive pill states from ``runs/{run_id}/`` artifacts.

    - Phase 1: ``query.json`` existence → query-generator done, all
      ``{source}-collect`` pills promoted to working.
    - Phase 2: any ``raw/*/{source}.json`` → ``{source}-collect`` done,
      ``{source}-validate`` working. ``validated/*/{source}.json`` →
      ``{source}-validate`` done (requires all products, falling back to any
      match when ``products`` isn't known yet).
    - Phase 3: ``report_{slug}.md`` for every product → reporter done.
    """
    root = RUNS_ROOT / run_id

    if (root / "query.json").exists() and job.agents.get("query-generator") != "error":
        job.agents["query-generator"] = "done"
        for sid in SOURCE_IDS:
            if job.agents.get(f"{sid}-collect") == "pending":
                job.agents[f"{sid}-collect"] = "working"

    products = _load_run_products(run_id)
    slugs = [_product_slug(p) for p in products]

    for sid in SOURCE_IDS:
        collect_key = f"{sid}-collect"
        validate_key = f"{sid}-validate"
        if job.agents.get(collect_key) == "error" and job.agents.get(validate_key) == "error":
            continue

        raw_hits = list(root.glob(f"raw/*/{sid}.json"))
        validated_hits = list(root.glob(f"validated/*/{sid}.json"))
        raw_slugs = {p.parent.name for p in raw_hits}
        validated_slugs = {p.parent.name for p in validated_hits}

        # Collect stage: all products have raw, OR (no product info yet) any raw.
        if job.agents.get(collect_key) != "done":
            if slugs and all(s in raw_slugs for s in slugs):
                job.agents[collect_key] = "done"
                if job.agents.get(validate_key) == "pending":
                    job.agents[validate_key] = "working"
            elif not slugs and raw_hits:
                job.agents[collect_key] = "done"
                if job.agents.get(validate_key) == "pending":
                    job.agents[validate_key] = "working"
            elif raw_hits and job.agents.get(collect_key) == "pending":
                job.agents[collect_key] = "working"

        # Validate stage: cascade — validated file implies collect is done.
        if job.agents.get(validate_key) != "done":
            done_all = slugs and all(s in validated_slugs for s in slugs)
            done_any_loose = not slugs and validated_hits
            if done_all or done_any_loose:
                job.agents[validate_key] = "done"
                if job.agents.get(collect_key) != "done":
                    job.agents[collect_key] = "done"
            elif validated_hits and job.agents.get(validate_key) != "working":
                job.agents[validate_key] = "working"

    # Phase 3: reporter
    if job.agents.get("reporter") != "error":
        md_hits = list(root.glob("report_*.md"))
        md_slugs = {m.stem.removeprefix("report_") for m in md_hits}
        if slugs and md_hits and all(s in md_slugs for s in slugs):
            job.agents["reporter"] = "done"
        elif md_hits and job.agents.get("reporter") in ("pending",):
            job.agents["reporter"] = "working"
        else:
            all_validated = all(
                job.agents.get(f"{sid}-validate") == "done" for sid in SOURCE_IDS
            )
            if all_validated and job.agents.get("reporter") == "pending":
                job.agents["reporter"] = "working"


async def _watch_run_progress(job: Job, run_id_holder: dict, stop_event: asyncio.Event) -> None:
    """Poll disk state until ``stop_event`` is set (A2A call finishes)."""
    # Visual phase 1 grace if run_id dir doesn't exist yet.
    qgen_deadline = time.time() + QUERY_GEN_VISUAL_DELAY_SECONDS
    while not stop_event.is_set():
        run_id = run_id_holder.get("value")
        if run_id is None:
            if time.time() > qgen_deadline and job.agents.get("query-generator") == "working":
                # Keep qgen visually working until we actually see query.json.
                pass
            await asyncio.sleep(0.5)
            continue
        _update_agents_from_run(job, run_id)
        await asyncio.sleep(0.5)


async def _run_live(job: Job) -> tuple[str, str]:
    """Kick off e2e over A2A, discover run_id from disk, drive 14-pill animation.

    Returns ``(run_id, concatenated_markdown)``. The e2e agent's ``plan_query``
    tool owns run_id allocation — we just send the raw query text and watch
    ``runs/`` for the new directory.
    """
    since = time.time()
    deadline = since + E2E_TIMEOUT_SECONDS

    e2e_task = asyncio.create_task(_a2a_send(E2E_URL, job.query, E2E_TIMEOUT_SECONDS))

    run_id_holder: dict[str, str | None] = {"value": None}

    async def _detect_and_store() -> None:
        rid = await _detect_run_id(since, deadline)
        if rid is not None:
            run_id_holder["value"] = rid
            job.run_id = rid  # expose to error handler before A2A returns

    detect_task = asyncio.create_task(_detect_and_store())

    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(
        _watch_run_progress(job, run_id_holder, stop_event)
    )

    try:
        response_text = await e2e_task
    finally:
        stop_event.set()
        for t in (detect_task, progress_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    run_id = run_id_holder.get("value")
    if run_id is None:
        m = _RUN_ID_RE.search(response_text or "")
        if m:
            run_id = m.group(1)

    if run_id is None:
        raise RuntimeError(
            "Could not determine run_id (no runs/{YYYYMMDD-HHMMSS-xxxxxxxx}/ "
            "directory created and no match in e2e response)"
        )

    _update_agents_from_run(job, run_id)
    for aid in job.agents:
        if job.agents[aid] in ("pending", "working"):
            job.agents[aid] = "done"

    markdown = _concat_run_reports(run_id)
    if not markdown.strip():
        markdown = response_text or "# (empty report)"
    return run_id, markdown


def _write_error_log(job: Job, exc: BaseException) -> Path | None:
    """Persist the full traceback + job context under the run's logs/ dir.

    Goes to ``runs/{run_id}/logs/ui-error.log`` when we captured a run_id before
    the failure; otherwise ``runs/_failed-{job_id}/logs/ui-error.log`` so the
    connect-before-e2e failure mode is still inspectable.
    """
    folder = job.run_id if job.run_id else f"_failed-{job.id}"
    log_dir = RUNS_ROOT / folder / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "ui-error.log"
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        body = (
            f"job_id: {job.id}\n"
            f"query:  {job.query}\n"
            f"mode:   {'STUB' if STUB_MODE else 'LIVE'}\n"
            f"e2e:    {E2E_URL}\n"
            f"run_id: {job.run_id or '(none — failure before run allocation)'}\n"
            f"agents: {json.dumps(job.agents, ensure_ascii=False)}\n"
            f"---\n{tb}"
        )
        log_file.write_text(body, encoding="utf-8")
        return log_file
    except OSError:
        return None


async def _run_job(job: Job) -> None:
    """Execute one job: phased pill animation + persist final markdown."""
    try:
        if STUB_MODE:
            markdown = await _run_stub(job)
            report_name = _new_report_name(job.query)
            (REPORTS_DIR / report_name).write_text(markdown, encoding="utf-8")
            job.report_name = report_name
        else:
            run_id, _markdown = await _run_live(job)
            # LIVE mode serves reports directly from runs/{run_id}/report_*.md
            # so report_name is the run_id itself (see /api/reports/{name}).
            job.run_id = run_id
            job.report_name = run_id
        job.status = "done"
    except Exception as exc:
        # On failure, any agent that hasn't completed is surfaced as error so
        # the user can tell something broke mid-flight.
        for aid, status in job.agents.items():
            if status in ("pending", "working"):
                job.agents[aid] = "error"
        log_file = _write_error_log(job, exc)
        suffix = f" (log: {log_file})" if log_file else ""
        job.error = f"{type(exc).__name__}: {exc}{suffix}"
        job.status = "error"


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
    )


@app.get("/api/reports/{name}", response_class=PlainTextResponse)
async def get_report(name: str) -> PlainTextResponse:
    # Block path traversal — accept only plain filenames.
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="invalid report name")

    # LIVE mode: name is a run_id (YYYYMMDD-HHMMSS-xxxxxxxx) — concatenate
    # every report_*.md in the run directory.
    if _RUN_ID_RE.fullmatch(name):
        root = (RUNS_ROOT / name).resolve()
        if not str(root).startswith(str(RUNS_ROOT)):
            raise HTTPException(status_code=400, detail="invalid run_id path")
        if not root.is_dir():
            raise HTTPException(status_code=404, detail="run not found")
        md = _concat_run_reports(name)
        if not md.strip():
            raise HTTPException(status_code=404, detail="no report_*.md in run")
        return PlainTextResponse(md, media_type="text/markdown")

    # STUB mode (or legacy): single markdown file under REPORTS_DIR.
    path = (REPORTS_DIR / name).resolve()
    if REPORTS_DIR not in path.parents and path.parent != REPORTS_DIR:
        raise HTTPException(status_code=400, detail="invalid report path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="report not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")


class HistoryItem(BaseModel):
    run_id: str
    user_query: str
    products: list[str]
    created_at: int


@app.get("/api/history", response_model=list[HistoryItem])
async def list_history() -> list[HistoryItem]:
    """Scan RUNS_ROOT for completed runs, newest first.

    Only returns runs with both ``query.json`` and at least one
    ``report_*.md`` — in-flight or failed runs are skipped.
    """
    items: list[HistoryItem] = []
    if not RUNS_ROOT.exists():
        return items
    for p in sorted(RUNS_ROOT.iterdir(), reverse=True):
        if not p.is_dir() or not _RUN_ID_RE.fullmatch(p.name):
            continue
        qf = p / "query.json"
        if not qf.is_file():
            continue
        if not any(p.glob("report_*.md")):
            continue
        try:
            q = json.loads(qf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        products = q.get("products") or []
        if not isinstance(products, list):
            products = []
        items.append(
            HistoryItem(
                run_id=p.name,
                user_query=str(q.get("user_query", "")) or "(no query)",
                products=[str(x) for x in products],
                created_at=int(p.stat().st_mtime),
            )
        )
    return items


@app.get("/api/config")
async def get_config() -> dict:
    return {
        "stub_mode": STUB_MODE,
        "e2e_url": E2E_URL,
        "reports_dir": str(REPORTS_DIR),
        "runs_root": str(RUNS_ROOT),
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
