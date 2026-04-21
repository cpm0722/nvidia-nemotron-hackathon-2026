"""NAT workflow: E2E pipeline — query-generator → collectors (parallel) → reporter.

Runs deterministically without an LLM-driven agent: each call executes
generate_queries → collect_evidence (per product, parallel across sources) →
generate_report in fixed order.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator

import requests
from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig


class E2EPipelineConfig(FunctionBaseConfig, name="e2e_pipeline"):
    """E2E pipeline 설정 (query-generator → collectors[N] → reporter 순차 실행).

    Args:
        query_generator_url: query-generator A2A 서버 URL.
        collector_urls: collector A2A 서버 URL 목록 (각 product마다 병렬 호출).
        reporter_url: reporter A2A 서버 URL.
        timeout_seconds: 각 A2A 호출당 타임아웃(초).
    """

    query_generator_url: str = Field(default="http://localhost:10001")
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
    reporter_url: str = Field(default="http://localhost:10002")
    timeout_seconds: int = Field(default=180, ge=30, le=600)


def _parse_product_list(raw: str) -> list[str] | None:
    """Extract a JSON list of product names from an LLM response.

    Handles reasoning-prefixed outputs like '<think>...</think>\\n["Gemma4"]' by
    stripping thinking blocks and grabbing the last top-level JSON array.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
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


def _a2a_send(url: str, message: str, timeout: int) -> str:
    """A2A v0.3 message/send 호출. Task/Message 양쪽 응답 모두 처리한다."""
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
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", {})
    artifacts = result.get("artifacts", [])
    if artifacts:
        parts = artifacts[0].get("parts", [])
        return parts[0].get("text", "") if parts else ""
    parts = result.get("parts", [])
    return parts[0].get("text", "") if parts else ""


@register_function(config_type=E2EPipelineConfig)
async def e2e_pipeline(
    config: E2EPipelineConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function LLM-less workflow orchestrating the 3-step pipeline."""

    async def _call_collector(url: str, product_name: str) -> dict:
        """Call one collector; return its ScrapeResult dict (ok=False on failure)."""
        try:
            raw = await asyncio.to_thread(
                _a2a_send, url, product_name, config.timeout_seconds
            )
            return json.loads(raw)
        except Exception as exc:
            return {"source": url, "ok": False, "items": [], "error": str(exc)}

    async def _collect_for_product(product_name: str) -> list[dict]:
        tasks = [_call_collector(url, product_name) for url in config.collector_urls]
        return await asyncio.gather(*tasks)

    async def run(user_query: str) -> str:
        """End-to-end pipeline: user_query → product names → evidence → report.

        Args:
            user_query: natural-language query (Korean or English), e.g.
                        "gemma4는 성능이 어때?" / "GPT5와 Gemma4 비교해줘".

        Returns:
            Final markdown report from the reporter agent.
        """
        qgen_raw = await asyncio.to_thread(
            _a2a_send, config.query_generator_url, user_query, config.timeout_seconds
        )
        products = _parse_product_list(qgen_raw)
        if products is None:
            return f"Failed to parse product names from query-generator: {qgen_raw}"

        if not products:
            return "No AI product names could be extracted from the query."

        evidence_per_product: dict[str, list[dict]] = {}
        for product in products:
            evidence_per_product[product] = await _collect_for_product(product)

        if len(products) == 1:
            product = products[0]
            report_input = (
                f"Product: {product}\n\nEvidence:\n"
                f"{json.dumps(evidence_per_product[product], ensure_ascii=False, indent=2, default=str)}"
            )
        else:
            report_input = "Products and evidence:\n" + json.dumps(
                evidence_per_product, ensure_ascii=False, indent=2, default=str
            )

        try:
            report = await asyncio.to_thread(
                _a2a_send, config.reporter_url, report_input, config.timeout_seconds
            )
        except Exception as exc:
            return f"Reporter error: {exc}"
        return report

    yield FunctionInfo.from_fn(
        fn=run,
        description=(
            "Run the full AI product feedback pipeline: extract product names via "
            "query-generator, collect evidence from all configured collectors in "
            "parallel, then synthesize a markdown report via the reporter."
        ),
    )
