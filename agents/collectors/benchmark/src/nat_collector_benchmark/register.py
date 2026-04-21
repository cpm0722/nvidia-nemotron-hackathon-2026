"""NAT workflow: benchmark collector — scrape then keyword-validate, no LLM."""

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

from nat_collector_benchmark.extractor import scrape as _scrape_benchmark
from nat_collector_benchmark.validator import filter_items


class BenchmarkCollectorConfig(FunctionBaseConfig, name="benchmark_collector"):
    """Benchmark Collector Agent 설정 (scrape → keyword validate 순차 실행)."""

    limit: int = Field(default=10, ge=1, le=100)
    comment_limit: int = Field(default=3, ge=0, le=20)


@register_function(config_type=BenchmarkCollectorConfig)
async def benchmark_collector(
    config: BenchmarkCollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Single-function workflow: scrape → keyword-validate → return ScrapeResult JSON."""

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={"comment_limit": config.comment_limit},
        )
        result = await asyncio.to_thread(_scrape_benchmark, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect benchmark scores and HF discussions for an LLM, filtered by keyword relevance.",
    )
