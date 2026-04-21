"""NAT workflow: geeknews collector — scrape then keyword-validate, no LLM."""

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

from nat_collector_geeknews.extractor import scrape as _scrape_geeknews
from nat_collector_geeknews.validator import filter_items


class GeekNewsCollectorConfig(FunctionBaseConfig, name="geeknews_collector"):
    """GeekNews Collector Agent 설정 (scrape → keyword validate 순차 실행)."""

    limit: int = Field(default=10, ge=1, le=30)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    enrich_html: bool = Field(default=True)
    include_comments: bool = Field(default=True)
    max_comments_per_topic: int = Field(default=10, ge=0, le=50)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    html_workers: int = Field(default=4, ge=1, le=8)


@register_function(config_type=GeekNewsCollectorConfig)
async def geeknews_collector(
    config: GeekNewsCollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape → keyword-validate → return ScrapeResult JSON."""

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={
            "enrich_html": config.enrich_html,
            "html_workers": config.html_workers,
            "max_text_chars": config.max_text_chars,
            "include_comments": config.include_comments,
            "max_comments_per_topic": config.max_comments_per_topic,
            "max_comment_chars": config.max_comment_chars,
        },
        )
        result = await asyncio.to_thread(_scrape_geeknews, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect GeekNews posts about an AI product and filter by keyword relevance.",
    )
