"""NAT workflow: reddit collector — scrape then keyword-validate, no LLM."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import ScrapeInput

from nat_collector_reddit.extractor import scrape as _scrape_reddit
from nat_collector_reddit.validator import filter_items


class RedditCollectorConfig(FunctionBaseConfig, name="reddit_collector"):
    """Reddit Collector Agent 설정 (scrape → keyword validate 순차 실행)."""

    subreddits: list[str] = Field(default_factory=lambda: ["LocalLLaMA", "MachineLearning", "ClaudeAI", "singularity"])
    limit: int = Field(default=10, ge=1, le=100)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    include_comments: bool = Field(default=True)
    max_comments_per_post: int = Field(default=5, ge=0, le=30)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    comment_workers: int = Field(default=3, ge=1, le=6)


@register_function(config_type=RedditCollectorConfig)
async def reddit_collector(
    config: RedditCollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape → keyword-validate → return ScrapeResult JSON."""

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
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
        result = await asyncio.to_thread(_scrape_reddit, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect Reddit posts about an AI product and filter by keyword relevance.",
    )
