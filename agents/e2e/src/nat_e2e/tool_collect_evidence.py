"""NAT tool: collect_evidence.

Fans out a ``{product, run_id}`` message to every configured collector A2A
endpoint in parallel. Each collector (extractor) internally scrapes, calls
its paired validator, persists both raw and validated JSON files under
``runs/{run_id}/``, and returns the validated file path as its response.

The tool aggregates those path strings into JSON
``{"run_id", "product", "paths"}`` for the orchestrator LLM. Individual
collector failures are silently dropped (best-effort) so one dead source
does not stop a run.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import a2a_send


class CollectEvidenceConfig(FunctionBaseConfig, name="collect_evidence"):
    """collect_evidence tool config.

    Args:
        collector_urls: A2A endpoints of all collector (extractor) agents.
        timeout_seconds: Per-collector HTTP timeout. Collectors scrape, then
            call an LLM validator, so 180–300s is typical.
    """

    collector_urls: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:10010",
            "http://localhost:10011",
            "http://localhost:10012",
            "http://localhost:10013",
            "http://localhost:10014",
            "http://localhost:10015",
            "http://localhost:10016",
        ]
    )
    timeout_seconds: int = Field(default=300, ge=30, le=1200)


class CollectEvidenceInput(BaseModel):
    """Input schema exposed to the react_agent."""

    run_id: str = Field(description="The run_id returned by plan_query.")
    product: str = Field(
        description="AI product/model name to collect evidence for (one name per call)."
    )


@register_function(config_type=CollectEvidenceConfig)
async def collect_evidence(
    config: CollectEvidenceConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Register the collect_evidence tool."""

    async def _call(url: str, message: str) -> str | None:
        try:
            return await asyncio.to_thread(
                a2a_send, url, message, config.timeout_seconds
            )
        except Exception:
            return None

    async def run(req: CollectEvidenceInput) -> str:
        message = json.dumps(
            {"product": req.product, "run_id": req.run_id}, ensure_ascii=False
        )
        results = await asyncio.gather(
            *[_call(url, message) for url in config.collector_urls]
        )
        paths = [r.strip() for r in results if r and r.strip()]
        return json.dumps(
            {"run_id": req.run_id, "product": req.product, "paths": paths},
            ensure_ascii=False,
        )

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Run all configured collector agents in parallel for an AI product. Each "
            "collector writes raw + validated JSON files under runs/{run_id}/ and "
            "returns the validated file path. Returns JSON {run_id, product, paths} "
            "with the list of validated file paths."
        ),
    )
