"""NAT workflow: lobsters collector — scrape then keyword-validate, no LLM."""

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

from nat_collector_lobsters.extractor import scrape as _scrape_lobsters
from nat_collector_lobsters.validator import filter_items


class LobstersCollectorConfig(FunctionBaseConfig, name="lobsters_collector"):
    """Lobsters Collector Agent 설정 (scrape → keyword validate 순차 실행)."""

    limit: int = Field(default=10, ge=1, le=50)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    enrich_json: bool = Field(default=True)
    include_comments: bool = Field(default=True)
    max_comments_per_story: int = Field(default=10, ge=0, le=50)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    workers: int = Field(default=4, ge=1, le=8)


@register_function(config_type=LobstersCollectorConfig)
async def lobsters_collector(
    config: LobstersCollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape → keyword-validate → return ScrapeResult JSON."""

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={
            "max_text_chars": config.max_text_chars,
            "enrich_json": config.enrich_json,
            "include_comments": config.include_comments,
            "max_comments_per_story": config.max_comments_per_story,
            "max_comment_chars": config.max_comment_chars,
            "workers": config.workers,
        },
        )
        result = await asyncio.to_thread(_scrape_lobsters, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect Lobsters posts about an AI product and filter by keyword relevance.",
    )
