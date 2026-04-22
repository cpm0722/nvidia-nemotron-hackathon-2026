"""NAT tool: write_report.

Forwards ``{product, run_id, paths}`` to the reporter A2A agent, which reads
each validated JSON file, synthesizes a markdown report via its LLM, writes
``runs/{run_id}/report_{product_slug}.md``, and returns the file path. This
tool simply surfaces that path back to the orchestrator LLM.
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


class WriteReportConfig(FunctionBaseConfig, name="write_report"):
    """write_report tool config.

    Args:
        reporter_url: A2A endpoint of the reporter agent.
        timeout_seconds: HTTP timeout; reporter calls a large LLM so allow
            a few minutes.
    """

    reporter_url: str = Field(default="http://localhost:10002")
    timeout_seconds: int = Field(default=300, ge=30, le=1200)


class WriteReportInput(BaseModel):
    """Input schema exposed to the react_agent."""

    run_id: str = Field(description="The run_id returned by plan_query.")
    product: str = Field(description="AI product/model name.")
    paths: list[str] = Field(
        description="Validated file paths returned by collect_evidence."
    )


@register_function(config_type=WriteReportConfig)
async def write_report(
    config: WriteReportConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Register the write_report tool."""

    async def run(req: WriteReportInput) -> str:
        message = json.dumps(
            {"product": req.product, "run_id": req.run_id, "paths": req.paths},
            ensure_ascii=False,
        )
        path = await asyncio.to_thread(
            a2a_send, config.reporter_url, message, config.timeout_seconds
        )
        return path.strip()

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Ask the reporter agent to synthesize a markdown report for a product "
            "from its validated evidence file paths. Returns the markdown file path "
            "(runs/{run_id}/report_{product}.md)."
        ),
    )
