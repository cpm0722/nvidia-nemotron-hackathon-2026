"""NAT workflow: reddit extractor — scrape then call validator A2A (no LLM here)."""

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

from nat_extractor_reddit.extractor import scrape as _scrape_reddit


class RedditExtractorConfig(FunctionBaseConfig, name="reddit_extractor"):
    """Reddit Extractor Agent 설정 (scrape → validator A2A 순차 호출)."""

    subreddits: list[str] = Field(default_factory=lambda: ["LocalLLaMA", "MachineLearning", "ClaudeAI", "singularity"])
    limit: int = Field(default=10, ge=1, le=100)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    include_comments: bool = Field(default=True)
    max_comments_per_post: int = Field(default=5, ge=0, le=30)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    comment_workers: int = Field(default=3, ge=1, le=6)
    validator_url: str = Field(default="http://localhost:10026")
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
    """Parse validator A2A response into a list of EvidenceItem; fall back on error."""
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


@register_function(config_type=RedditExtractorConfig)
async def reddit_extractor(
    config: RedditExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape reddit, then forward items to the validator A2A."""

    async def collect(product_name: str) -> str:
        scrape_input = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={
            "subreddits": config.subreddits,
            "max_text_chars": config.max_text_chars,
            "include_comments": config.include_comments,
            "max_comments_per_post": config.max_comments_per_post,
            "max_comment_chars": config.max_comment_chars,
            "comment_workers": config.comment_workers,
        },
        )
        result = await asyncio.to_thread(_scrape_reddit, scrape_input)

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
                pass

        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Scrape Reddit posts for an AI product and validate via the validator A2A.",
    )
