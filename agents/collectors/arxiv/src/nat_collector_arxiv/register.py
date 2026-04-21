"""NAT workflow: arxiv collector — scrape then keyword-validate, no LLM."""

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

from nat_collector_arxiv.extractor import scrape as _scrape_arxiv
from nat_collector_arxiv.validator import filter_items


class ArxivCollectorConfig(FunctionBaseConfig, name="arxiv_collector"):
    """arXiv Collector Agent 설정 (scrape → keyword validate 순차 실행)."""

    limit: int = Field(default=10, ge=1, le=50)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)


@register_function(config_type=ArxivCollectorConfig)
async def arxiv_collector(
    config: ArxivCollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape → keyword-validate → return ScrapeResult JSON."""

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={"max_text_chars": config.max_text_chars},
        )
        result = await asyncio.to_thread(_scrape_arxiv, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect arXiv papers about an AI topic/product and filter by keyword relevance.",
    )
