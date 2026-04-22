"""NAT workflow: benchmark extractor — scrape, write raw file, validate, write validated file.

Input (A2A message text, JSON):
    {"product": "GPT-5", "run_id": "20260422-120000-deadbeef"}

Output: filesystem path to the validated result JSON (a single string).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import (
    ScrapeInput,
    a2a_send,
    parse_collect_input,
    parse_validator_response,
    raw_path,
    validated_path,
    write_json,
)

from nat_extractor_benchmark.extractor import scrape as _scrape_benchmark

SOURCE_NAME = "benchmark"


class BenchmarkExtractorConfig(FunctionBaseConfig, name="benchmark_extractor"):
    """Benchmark extractor 설정 (scrape → write raw → validator A2A → write validated)."""

    limit: int = Field(default=10, ge=1, le=100)
    comment_limit: int = Field(default=3, ge=0, le=20)
    validator_url: str = Field(default="http://localhost:10022")
    validator_timeout_seconds: int = Field(default=120, ge=10, le=600)


@register_function(config_type=BenchmarkExtractorConfig)
async def benchmark_extractor(
    config: BenchmarkExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Collect benchmark + HF discussion evidence; persist raw + validated; return validated path."""

    async def collect(raw_input: str) -> str:
        product, run_id = parse_collect_input(raw_input)
        raw_file = raw_path(run_id, product, SOURCE_NAME)
        validated_file = validated_path(run_id, product, SOURCE_NAME)

        scrape_input = ScrapeInput(
            query=product,
            limit=config.limit,
            extra={"comment_limit": config.comment_limit},
        )
        result = await asyncio.to_thread(_scrape_benchmark, scrape_input)
        write_json(raw_file, result.model_dump())

        if result.ok and result.items:
            items_json = json.dumps(
                [it.model_dump() for it in result.items],
                ensure_ascii=False,
                default=str,
            )
            message = f"Product: {product}\n\nScraped data:\n{items_json}"
            try:
                validator_text = await asyncio.to_thread(
                    a2a_send,
                    config.validator_url,
                    message,
                    config.validator_timeout_seconds,
                )
                result.items = parse_validator_response(validator_text, result.items)
            except Exception:
                pass

        write_json(validated_file, result.model_dump())
        return str(validated_file)

    yield FunctionInfo.from_fn(
        fn=collect,
        description=(
            "Collect benchmark scores and HF discussions for an AI product, validate via "
            "the validator A2A, persist both raw and validated JSON under runs/{run_id}/, "
            "and return the validated file path."
        ),
    )
