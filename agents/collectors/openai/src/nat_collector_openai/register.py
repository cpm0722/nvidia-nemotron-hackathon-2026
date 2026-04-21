"""NAT workflow: openai collector — scrape then keyword-validate, no LLM."""

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

from nat_collector_openai.extractor import scrape as _scrape_openai
from nat_collector_openai.validator import filter_items


class OpenAICollectorConfig(FunctionBaseConfig, name="openai_collector"):
    """OpenAI Blog Collector Agent 설정 (scrape → keyword validate 순차 실행)."""

    limit: int = Field(default=10, ge=1, le=50)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)


@register_function(config_type=OpenAICollectorConfig)
async def openai_collector(
    config: OpenAICollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape → keyword-validate → return ScrapeResult JSON."""

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={"max_text_chars": config.max_text_chars},
        )
        result = await asyncio.to_thread(_scrape_openai, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect OpenAI blog posts about an AI product and filter by keyword relevance.",
    )
