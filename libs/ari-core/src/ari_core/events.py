"""HTTP event emitter for pipeline progress streaming.

Tools call :func:`emit_event` to push human-readable progress messages back to
the UI backend. The target endpoint and job_id are stored in per-async-context
:class:`~contextvars.ContextVar` slots, set once per request via
:func:`set_event_context` — typically from the tool that first parsed the UI
envelope, or from an extractor/reporter that received the envelope fields in
its A2A message.

Transport: HTTP POST to ``event_url``. Fire-and-forget with a 1-second timeout
— event delivery must never block the pipeline's critical path, because UI
outage should not degrade data collection.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

EventType = Literal["start", "progress", "complete", "error"]
EventPhase = Literal["plan", "collect", "report"]

_event_url: ContextVar[str | None] = ContextVar("ari_event_url", default=None)
_job_id: ContextVar[str | None] = ContextVar("ari_job_id", default=None)

EMIT_TIMEOUT_SECONDS = 1.0


def set_event_context(event_url: str | None, job_id: str | None) -> None:
    """Set the pipeline event-streaming context for the current async task.

    Call once at the entry point of any tool/agent that received an envelope
    containing ``event_url`` + ``job_id``. Subsequent :func:`emit_event` calls
    in the same asyncio task (including awaited sub-tasks) will target the
    given UI backend.

    Passing ``None`` for either field disables streaming — useful in unit
    tests and for CLI invocations that don't wrap their query.

    Args:
        event_url: Full POST URL ending in ``/api/events/{job_id}``, or None.
        job_id: UI job identifier (echoed into every event payload), or None.
    """
    _event_url.set(event_url)
    _job_id.set(job_id)


def get_event_context() -> tuple[str | None, str | None]:
    """Return the current ``(event_url, job_id)`` pair; both may be ``None``."""
    return _event_url.get(), _job_id.get()


def build_event_payload(
    *,
    agent: str,
    event_type: EventType,
    phase: EventPhase | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an event dict in the shared wire-schema shape.

    Exposed separately from :func:`emit_event` so callers (and tests) can
    construct and inspect payloads without network I/O.
    """
    return {
        "ts": time.time(),
        "job_id": _job_id.get(),
        "agent": agent,
        "phase": phase,
        "type": event_type,
        "message": message,
        "data": data or {},
    }


async def emit_event(
    *,
    agent: str,
    event_type: EventType,
    phase: EventPhase | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    """POST a progress event to the UI backend configured in the current context.

    No-ops when :func:`set_event_context` was never called in this task (tests,
    STUB-mode local runs, CLI). Transport errors are logged as warnings and
    swallowed — event streaming is best-effort and must not propagate failure
    into tool logic.

    Args:
        agent: Pill ``data-id`` (e.g. ``"arcalive"``) or phase-level tool name
            (``"plan_query"``, ``"collect_evidence"``, ``"write_report"``).
        event_type: One of ``"start"``, ``"progress"``, ``"complete"``,
            ``"error"``.
        phase: ``"plan"``/``"collect"``/``"report"`` when the event represents
            a phase-level transition; omit for agent-scoped events.
        message: Human-readable text shown under the pill.
        data: Optional structured payload (counts, urls, etc.) — consumers may
            read specific keys for richer rendering.
    """
    url = _event_url.get()
    jid = _job_id.get()
    if not url or not jid:
        return
    payload = build_event_payload(
        agent=agent,
        event_type=event_type,
        phase=phase,
        message=message,
        data=data,
    )
    try:
        async with httpx.AsyncClient(timeout=EMIT_TIMEOUT_SECONDS) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning(
            "emit_event failed (agent=%s type=%s url=%s): %s",
            agent,
            event_type,
            url,
            exc,
        )
