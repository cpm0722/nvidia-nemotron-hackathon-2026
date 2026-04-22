"""NAT tool: plan_query.

Calls the query-generator A2A service, extracts the AI product name list from
its response, allocates a new ``run_id``, persists ``runs/{run_id}/query.json``
with both the original user query and the extracted products, and returns a
JSON string ``{"run_id": ..., "products": [...]}`` for the orchestrator LLM
to feed into the next tool.

The query-generator is itself an LLM and may wrap its answer in
``<think>...</think>`` reasoning. ``_parse_product_list`` strips that and
finds the last top-level JSON array in the response.

The ``user_query`` input is the raw UI envelope (JSON) when invoked from the
browser pipeline; :func:`ari_core.parse_envelope` extracts ``job_id`` and
``event_url`` so subsequent tool calls in the same e2e process — and the
extractors / reporter dispatched from them — can stream progress events to
the UI under the same chat bubble.
"""

import asyncio
import json
import re
from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import (
    a2a_send,
    emit_event,
    new_run_id,
    parse_envelope,
    query_path,
    set_event_context,
    write_json,
)

_THINK_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL)


class PlanQueryConfig(FunctionBaseConfig, name="plan_query"):
    """plan_query tool config.

    Args:
        query_generator_url: A2A endpoint of the query-generator agent.
        timeout_seconds: HTTP timeout for the A2A call.
    """

    query_generator_url: str = Field(default="http://localhost:10001")
    timeout_seconds: int = Field(default=180, ge=30, le=600)


class PlanQueryInput(BaseModel):
    """Input schema exposed to the react_agent."""

    user_query: str = Field(
        description=(
            "User's natural-language query (Korean or English). The browser UI "
            "wraps this in a JSON envelope {query, job_id, event_url, work_dir}; "
            "pass that envelope through verbatim — the tool parses it internally."
        )
    )


def _parse_product_list(raw: str) -> list[str] | None:
    """Extract the product-name JSON list from an LLM response.

    Handles reasoning-prefixed outputs like ``<think>...</think>\\n["Gemma4"]``
    by stripping thinking blocks and returning the last top-level JSON array.

    Returns:
        The parsed list or ``None`` when the response is not JSON-decodable.
    """
    cleaned = _THINK_RE.sub("", raw).strip()
    try:
        value = json.loads(cleaned)
        if isinstance(value, list):
            return [str(x) for x in value]
    except json.JSONDecodeError:
        pass
    match = None
    for m in re.finditer(r"\[[^\[\]]*\]", cleaned, flags=re.DOTALL):
        match = m
    if match:
        try:
            value = json.loads(match.group(0))
            if isinstance(value, list):
                return [str(x) for x in value]
        except json.JSONDecodeError:
            return None
    return None


@register_function(config_type=PlanQueryConfig)
async def plan_query(
    config: PlanQueryConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Register the plan_query tool."""

    async def run(req: PlanQueryInput) -> str:
        envelope = parse_envelope(req.user_query)
        # Bind UI streaming context for this task so collect_evidence /
        # write_report (same async task) inherit without explicit plumbing.
        set_event_context(envelope.event_url, envelope.job_id)

        user_query = envelope.query or req.user_query
        await emit_event(
            agent="query-generator",
            event_type="start",
            phase="plan",
            message="Extracting product names…",
        )
        raw = await asyncio.to_thread(
            a2a_send,
            config.query_generator_url,
            user_query,
            config.timeout_seconds,
        )
        products = _parse_product_list(raw) or []
        run_id = new_run_id()
        write_json(
            query_path(run_id),
            {"user_query": user_query, "products": products},
        )
        await emit_event(
            agent="query-generator",
            event_type="complete",
            phase="plan",
            message=f"{len(products)} product(s) identified"
            + (f": {', '.join(products)}" if products else ""),
            data={"products": products, "run_id": run_id},
        )
        return json.dumps(
            {"run_id": run_id, "products": products}, ensure_ascii=False
        )

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Use the query-generator to extract AI product/model names from a natural "
            "language query, allocate a new run_id, persist runs/{run_id}/query.json, "
            "and return JSON with the run_id and products array. IMPORTANT: pass the "
            "user_query exactly as received from the user (do not unwrap any JSON "
            "envelope) — the tool parses the envelope internally and needs its "
            "streaming context."
        ),
    )
