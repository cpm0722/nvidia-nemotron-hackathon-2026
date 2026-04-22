"""NAT workflow: file-based report generator.

Input (A2A message text, JSON)::

    {
      "product": "GPT-5",
      "run_id": "20260422-120000-deadbeef",
      "paths": ["runs/.../validated/gpt-5/reddit.json", ...]
    }

The workflow reads each validated ScrapeResult JSON from ``paths``, concatenates
them as evidence context, invokes the configured LLM (nemotron-3-super) with
the system prompt, then post-processes the LLM output:

1. Strips a leading Nemotron-Super reasoning block that ends with ``</think>``.
2. Extracts the final ```json`` fenced block (structured report payload).
3. Writes the markdown portion to ``runs/{run_id}/report_{product_slug}.md``.
4. Writes the parsed JSON portion to ``runs/{run_id}/report_{product_slug}.json``.

Returns a JSON string ``{"report_md": "<path>", "report_json": "<path>"}``
so the orchestrator / frontend can locate both artifacts deterministically.

Keeping file I/O inside this workflow (rather than at the orchestrator layer)
means the reporter's contract to callers is "give me paths, get paths back",
which matches the pattern used by the per-source collectors.
"""

import json
import re
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

from ari_core import report_json_path, report_path, write_json, write_text

# Strip everything up to and including the first </think> tag (Nemotron-Super
# thinking-mode prefix). Applied at the start of the raw LLM response.
_THINK_RE = re.compile(r"(?s)^.*?</think>\s*")

# Capture the LAST ```json ... ``` fenced block in the response body. We take
# the last one so if the model embeds JSON in reasoning text earlier, we still
# pick up the final payload.
_JSON_FENCE_RE = re.compile(r"(?s)```json\s*\n(\{.*?\})\s*```")


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


def _split_report(raw: str) -> tuple[str, dict | None, str | None]:
    """Split a raw LLM response into (markdown, parsed_json, parse_error).

    1. Drop any leading ``...</think>`` reasoning block.
    2. Find the last ```json`` fenced block; parse it.
    3. Markdown = the response with the fenced block stripped (and the think
       prefix already removed).

    If no JSON fence is present or parsing fails, the parsed JSON is ``None``
    and an error string is returned; the markdown is still returned so the
    human-readable artifact is never lost.
    """
    cleaned = _THINK_RE.sub("", raw, count=1)

    parsed: dict | None = None
    parse_error: str | None = None
    match = None
    for m in _JSON_FENCE_RE.finditer(cleaned):
        match = m  # keep iterating so the last match wins
    if match is None:
        parse_error = "no fenced json block found"
        md = cleaned.strip()
    else:
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            parse_error = f"fenced json parse failed: {exc}"
        md = (cleaned[: match.start()] + cleaned[match.end():]).strip()

    return md, parsed, parse_error


@register_function(config_type=ReportGeneratorConfig)
async def report_generator(
    config: ReportGeneratorConfig, builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Read validated JSON files, call the LLM, write markdown + JSON artifacts, return their paths."""
    llm = await builder.get_llm(config.llm_name, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

    async def generate(raw_input: str) -> str:
        try:
            data = json.loads(raw_input)
        except json.JSONDecodeError as exc:
            return f"Reporter input must be JSON: {exc}"
        if not isinstance(data, dict):
            return "Reporter input must be a JSON object"

        product = data.get("product") or data.get("product_name")
        run_id = data.get("run_id")
        paths = data.get("paths")
        if not product or not run_id or not isinstance(paths, list):
            return "Reporter input missing 'product', 'run_id', or 'paths' list"

        evidence = _load_evidence([str(p) for p in paths])
        user_text = (
            f"Product: {product}\n\nEvidence:\n"
            f"{json.dumps(evidence, ensure_ascii=False, indent=2, default=str)}"
        )

        messages = [
            SystemMessage(content=config.system_prompt),
            HumanMessage(content=user_text),
        ]
        response = await llm.ainvoke(messages)
        raw = (
            response.text()
            if hasattr(response, "text")
            else str(getattr(response, "content", response))
        )

        md_text, report_obj, parse_error = _split_report(raw)

        md_out = report_path(run_id, product)
        json_out = report_json_path(run_id, product)

        write_text(md_out, md_text + "\n")

        if report_obj is not None:
            # Enrich with run-level context the LLM doesn't know so the JSON
            # file is self-contained for the frontend.
            report_obj.setdefault("run_id", run_id)
            write_json(json_out, report_obj)
        else:
            # Save a stub JSON so downstream consumers never see a missing file.
            write_json(
                json_out,
                {
                    "run_id": run_id,
                    "product": product,
                    "error": parse_error or "unknown parse error",
                    "raw_markdown_path": str(md_out),
                },
            )

        return json.dumps(
            {"report_md": str(md_out), "report_json": str(json_out)},
            ensure_ascii=False,
        )

    yield FunctionInfo.from_fn(
        fn=generate,
        description=(
            "Read validated evidence JSON files for one AI product, synthesize a markdown "
            "report plus a structured JSON sidecar via the configured LLM, persist them "
            "to runs/{run_id}/report_{product}.md and runs/{run_id}/report_{product}.json, "
            "and return both paths as a JSON string."
        ),
    )
