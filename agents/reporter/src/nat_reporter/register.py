"""NAT workflow: file-based report generator.

Input (A2A message text, JSON)::

    {
      "product": "GPT-5",
      "run_id": "20260422-120000-deadbeef",
      "paths": ["runs/.../validated/gpt-5/reddit.json", ...],
      "job_id": "<ui-job>",
      "event_url": "http://ui:8080/api/events/<ui-job>"
    }

``job_id`` / ``event_url`` are optional — populated only when the pipeline
was triggered from the browser UI. When present, the workflow emits its own
progress events (loading evidence, invoking LLM, writing file) so the UI's
reporter pill shows something other than a silent multi-minute wait.

The workflow reads each validated ScrapeResult JSON from ``paths``, concatenates
them as evidence context, invokes the configured LLM (nemotron-3-super) with
the system prompt, and persists the resulting markdown to
``runs/{run_id}/report_{product_slug}.md``. The output is the path string.

Keeping file I/O inside this workflow (rather than at the orchestrator layer)
means the reporter's contract to callers is "give me paths, get a path back",
which matches the pattern used by the per-source collectors.
"""

import json
from collections.abc import AsyncGenerator
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import LLMRef
from nat.data_models.function import FunctionBaseConfig

from ari_core import emit_event, parse_envelope, report_path, set_event_context, write_text

AGENT_NAME = "reporter"


class ReportGeneratorConfig(FunctionBaseConfig, name="report_generator"):
    """File-based report generator config.

    Args:
        llm_name: LLMRef to the chat model (typically nemotron-3-super).
        system_prompt: System prompt text. YAML ``file://`` references are
            resolved automatically by NAT's yaml_tools.
    """

    llm_name: LLMRef = Field(description="LLM reference used for synthesis.")
    system_prompt: str = Field(
        default="You are a senior AI analyst synthesizing evidence into a report."
    )


def _load_evidence(paths: list[str]) -> list[dict]:
    """Read each validated ScrapeResult JSON from disk; fall back to error blob on failure.

    A missing / malformed file is surfaced as ``{"source": path, "ok": false, "error": ...}``
    so the reporter LLM can still reason about which source was unavailable
    instead of the whole run failing.
    """
    blobs: list[dict] = []
    for p in paths:
        try:
            blobs.append(json.loads(Path(p).read_text(encoding="utf-8")))
        except Exception as exc:
            blobs.append({"source": p, "ok": False, "error": str(exc), "items": []})
    return blobs


@register_function(config_type=ReportGeneratorConfig)
async def report_generator(
    config: ReportGeneratorConfig, builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Read validated JSON files, call the LLM, write the markdown report, return its path."""
    llm = await builder.get_llm(config.llm_name, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

    async def generate(raw_input: str) -> str:
        env = parse_envelope(raw_input)
        set_event_context(env.event_url, env.job_id)
        try:
            data = json.loads(raw_input)
        except json.JSONDecodeError as exc:
            await emit_event(
                agent=AGENT_NAME, event_type="error", phase="report",
                message=f"reporter: invalid JSON input — {exc}",
            )
            return f"Reporter input must be JSON: {exc}"
        if not isinstance(data, dict):
            await emit_event(
                agent=AGENT_NAME, event_type="error", phase="report",
                message="reporter: input must be a JSON object",
            )
            return "Reporter input must be a JSON object"

        product = data.get("product") or data.get("product_name")
        run_id = data.get("run_id")
        paths = data.get("paths")
        if not product or not run_id or not isinstance(paths, list):
            await emit_event(
                agent=AGENT_NAME, event_type="error", phase="report",
                message="reporter: missing product/run_id/paths",
            )
            return "Reporter input missing 'product', 'run_id', or 'paths' list"

        await emit_event(
            agent=AGENT_NAME, event_type="start", phase="report",
            message=f"reporter: loading {len(paths)} evidence files…",
            data={"path_count": len(paths), "product": product},
        )
        evidence = _load_evidence([str(p) for p in paths])
        ok_count = sum(1 for blob in evidence if blob.get("ok", True))
        await emit_event(
            agent=AGENT_NAME, event_type="progress", phase="report",
            message=f"reporter: {ok_count}/{len(evidence)} sources loaded, invoking LLM…",
            data={"ok_sources": ok_count, "total_sources": len(evidence)},
        )

        user_text = (
            f"Product: {product}\n\nEvidence:\n"
            f"{json.dumps(evidence, ensure_ascii=False, indent=2, default=str)}"
        )

        messages = [
            SystemMessage(content=config.system_prompt),
            HumanMessage(content=user_text),
        ]
        try:
            response = await llm.ainvoke(messages)
        except Exception as exc:
            await emit_event(
                agent=AGENT_NAME, event_type="error", phase="report",
                message=f"reporter: LLM synthesis failed — {exc}",
            )
            raise
        text = (
            response.text()
            if hasattr(response, "text")
            else str(getattr(response, "content", response))
        )

        out_path = report_path(run_id, product)
        write_text(out_path, text)
        await emit_event(
            agent=AGENT_NAME, event_type="complete", phase="report",
            message=f"reporter: briefing written ({len(text)} chars)",
            data={"report_path": str(out_path), "length": len(text)},
        )
        return str(out_path)

    yield FunctionInfo.from_fn(
        fn=generate,
        description=(
            "Read validated evidence JSON files for an AI product, synthesize a markdown "
            "report via the configured LLM, persist it to runs/{run_id}/report_{product}.md, "
            "and return the report file path."
        ),
    )
