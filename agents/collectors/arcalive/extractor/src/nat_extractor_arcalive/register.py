"""NAT workflow: arcalive extractor — scrape then call validator A2A (no LLM here)."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import requests
from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import EvidenceItem, ScrapeInput

from nat_extractor_arcalive.extractor import scrape as _scrape_arcalive


class ArcaliveExtractorConfig(FunctionBaseConfig, name="arcalive_extractor"):
    """arca.live extractor 설정 (scrape → validator A2A 순차 호출).

    Args:
        board: Arcalive channel slug to search.
        max_pages: Maximum search result pages to crawl.
        limit: Maximum posts to return.
        validator_url: Validator A2A endpoint; called with scraped items.
        validator_timeout_seconds: HTTP timeout for the validator call.
    """

    board: str = Field(default="alpaca")
    max_pages: int = Field(default=2)
    limit: int = Field(default=5, ge=1, le=20)
    validator_url: str = Field(default="http://localhost:10020")
    validator_timeout_seconds: int = Field(default=120, ge=10, le=600)


def _a2a_send(url: str, message: str, timeout: int) -> str:
    """A2A v0.3 message/send call; returns the response text (Task or Message shape)."""
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


_THINK_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.MULTILINE)


def _parse_validator_response(text: str, fallback: list[EvidenceItem]) -> list[EvidenceItem]:
    """Parse validator A2A response into a list of EvidenceItem; fall back on error.

    Accepts responses wrapped in <think>...</think>, markdown fences, or a JSON
    object whose first list-valued field contains the items.
    """
    cleaned = _THINK_RE.sub("", text).strip()
    cleaned = _FENCE_RE.sub("", cleaned).strip()

    parsed: Any = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", cleaned)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return fallback

    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                parsed = value
                break
        else:
            return fallback

    if not isinstance(parsed, list):
        return fallback

    result: list[EvidenceItem] = []
    for obj in parsed:
        if not isinstance(obj, dict):
            continue
        try:
            result.append(EvidenceItem(**obj))
        except Exception:
            continue
    return result if result else fallback


@register_function(config_type=ArcaliveExtractorConfig)
async def arcalive_extractor(
    config: ArcaliveExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape arca.live, then forward items to the validator A2A."""

    async def collect(product_name: str) -> str:
        scrape_input = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={"board": config.board, "max_pages": config.max_pages},
        )
        result = await asyncio.to_thread(_scrape_arcalive, scrape_input)

        if result.ok and result.items:
            items_json = json.dumps(
                [it.model_dump() for it in result.items], ensure_ascii=False, default=str
            )
            message = f"Product: {product_name}\n\nScraped data:\n{items_json}"
            try:
                validator_text = await asyncio.to_thread(
                    _a2a_send, config.validator_url, message, config.validator_timeout_seconds
                )
                result.items = _parse_validator_response(validator_text, result.items)
            except Exception:
                pass  # fall back to unfiltered items

        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Scrape arca.live for an AI product and validate items via the validator A2A.",
    )
