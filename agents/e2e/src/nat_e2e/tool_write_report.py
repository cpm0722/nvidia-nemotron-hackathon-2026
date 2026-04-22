"""NAT tool: write_report.

Forwards ``{product, run_id, paths, job_id?, event_url?}`` to the reporter
A2A agent, which reads each validated JSON file, synthesizes a markdown
report via its LLM, writes ``runs/{run_id}/report_{product_slug}.md``, and
returns the file path. The reporter emits its own progress events to the
UI using the forwarded ``event_url`` / ``job_id``.
"""

import asyncio
from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import (
    Envelope,
    a2a_send,
    emit_event,
    get_event_context,
    serialize_downstream_message,
)


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
        event_url, job_id = get_event_context()
        envelope = Envelope(job_id=job_id, event_url=event_url)
        message = serialize_downstream_message(
            envelope,
            product=req.product,
            run_id=req.run_id,
            paths=req.paths,
        )
        await emit_event(
            agent=None,
            event_type="start",
            phase="report",
            message=f"Synthesizing briefing from {len(req.paths)} evidence files…",
            data={"path_count": len(req.paths)},
        )
        path = await asyncio.to_thread(
            a2a_send, config.reporter_url, message, config.timeout_seconds
        )
        path = path.strip()
        await emit_event(
            agent=None,
            event_type="complete",
            phase="report",
            message="Briefing saved",
            data={"report_path": path},
        )
        return path

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Ask the reporter agent to synthesize a markdown report for a product "
            "from its validated evidence file paths. Returns the markdown file path "
            "(runs/{run_id}/report_{product}.md)."
        ),
    )
