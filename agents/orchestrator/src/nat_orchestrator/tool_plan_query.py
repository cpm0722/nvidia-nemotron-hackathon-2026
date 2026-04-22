"""NAT tool: plan_query.

Calls the query-generator A2A service, extracts the AI product name list from
its response, allocates a new ``run_id``, persists ``runs/{run_id}/query.json``
with both the original user query and the extracted products, and returns a
JSON string ``{"run_id": ..., "products": [...]}`` for the orchestrator LLM
to feed into the next tool.

The query-generator is itself an LLM and may wrap its answer in
``<think>...</think>`` reasoning. ``_parse_product_list`` strips that and
finds the last top-level JSON array in the response.
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

from ari_core import a2a_send, new_run_id, query_path, write_json

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
        description="User's natural-language query (Korean or English). Example: 'GPT5와 Gemma4 비교'."
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
        raw = await asyncio.to_thread(
            a2a_send,
            config.query_generator_url,
            req.user_query,
            config.timeout_seconds,
        )
        products = _parse_product_list(raw) or []
        run_id = new_run_id()
        write_json(
            query_path(run_id),
            {"user_query": req.user_query, "products": products},
        )
        return json.dumps(
            {"run_id": run_id, "products": products}, ensure_ascii=False
        )

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Use the query-generator to extract AI product/model names from a natural "
            "language query, allocate a new run_id, persist runs/{run_id}/query.json, "
            "and return JSON with the run_id and products array."
        ),
    )
