"""Parse UI-originated A2A envelopes into pipeline streaming context.

The browser UI wraps every query in a JSON envelope so downstream tools can
echo progress events back::

    {"query": "GPT5와 Gemma4 비교", "job_id": "<uuid>",
     "event_url": "http://ui:8080/api/events/<uuid>", "work_dir": "..."}

e2e's ``plan_query`` receives the raw envelope as its ``user_query`` string.
Extractor and reporter A2A messages carry the same ``job_id``/``event_url``
fields alongside their existing ``{product, run_id, paths?}`` payload.

:func:`parse_envelope` is a forgiving parser: any shape that isn't a JSON
object is treated as a plain query with no streaming context, keeping the
legacy CLI / curl invocations working.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Envelope:
    """Streaming-aware message envelope.

    Attributes:
        query: Natural-language user query (only populated on the e2e entry;
            extractor/reporter inputs leave this empty).
        job_id: UI job identifier; pairs every event with its chat bubble.
        event_url: Full POST URL the pipeline targets for progress events.
        work_dir: UI scratch directory (retained for backward compatibility;
            new code should not rely on it).
    """

    query: str = ""
    job_id: str | None = None
    event_url: str | None = None
    work_dir: str | None = None


def _str_or_none(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_envelope(raw: str) -> Envelope:
    """Parse an A2A input string into :class:`Envelope`.

    Accepts either a JSON object wrapping ``query``/``job_id``/``event_url``/
    ``work_dir`` (UI-originated), or a bare string (CLI / manual A2A call). In
    the bare-string case the whole text becomes :attr:`Envelope.query` and all
    streaming-context fields are ``None``.

    Args:
        raw: The raw ``user_query`` text or A2A message body.

    Returns:
        An :class:`Envelope` with whichever fields were decodable; missing
        keys stay at their dataclass defaults.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return Envelope(query=raw.strip())
    if not isinstance(data, dict):
        return Envelope(query=str(data).strip())
    query = data.get("query") or data.get("user_query") or ""
    return Envelope(
        query=str(query).strip(),
        job_id=_str_or_none(data.get("job_id")),
        event_url=_str_or_none(data.get("event_url")),
        work_dir=_str_or_none(data.get("work_dir")),
    )


def serialize_downstream_message(
    envelope: Envelope,
    *,
    product: str | None = None,
    run_id: str | None = None,
    paths: list[str] | None = None,
) -> str:
    """Build a JSON A2A message that forwards envelope streaming context.

    Used by e2e tools when dispatching to extractors or the reporter: packs
    the pipeline-required fields (``product``/``run_id``/``paths``) together
    with ``job_id``/``event_url`` so the downstream agent can attach its own
    events to the same UI job.

    Args:
        envelope: The current request's envelope (from :func:`parse_envelope`
            or rehydrated from contextvars by the caller).
        product: AI product name, included when non-``None``.
        run_id: Pipeline run id, included when non-``None``.
        paths: Validated-JSON path list (reporter input), included when
            non-``None``.

    Returns:
        A compact JSON string ready to pass as an A2A message body.
    """
    payload: dict[str, object] = {}
    if product is not None:
        payload["product"] = product
    if run_id is not None:
        payload["run_id"] = run_id
    if paths is not None:
        payload["paths"] = paths
    if envelope.job_id:
        payload["job_id"] = envelope.job_id
    if envelope.event_url:
        payload["event_url"] = envelope.event_url
    return json.dumps(payload, ensure_ascii=False)
