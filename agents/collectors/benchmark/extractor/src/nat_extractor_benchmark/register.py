"""NAT workflow: benchmark extractor — scrape, write raw, validate via validator_core, write validated.

Input (A2A message text, JSON):
    {"product": "GPT-5", "run_id": "20260422-120000-deadbeef"}

Output: filesystem path to the validated result JSON (a single string).

Uses validator_core.validate_items for robust parsing (orphan </think>, balanced
bracket scan, truncation detection), URL-keyed merge of relevance decisions,
and slim-payload serialization (clipped text + match-centered comment windowing).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from ari_core import (
    ScrapeInput,
    parse_collect_input,
    raw_path,
    validated_path,
    write_json,
)
from validator_core import ClientConfig, validate_items

from nat_extractor_benchmark.extractor import scrape as _scrape_benchmark

SOURCE_NAME = "benchmark"


class BenchmarkExtractorConfig(FunctionBaseConfig, name="benchmark_extractor"):
    """benchmark extractor 설정 (scrape → raw write → validator_core → validated write)."""

    limit: int = Field(default=10, ge=1, le=100)
    comment_limit: int = Field(default=3, ge=0, le=20)
    validator_url: str = Field(default="http://localhost:10022")
    validator_timeout_seconds: int = Field(default=120, ge=10, le=600)
    validator_max_text_chars: int = Field(default=2500, ge=200, le=8000,
        description="Clip item.text before sending to validator; controls prompt size.")
    validator_min_relevance_score: float = Field(default=0.5, ge=0.0, le=1.0,
        description="Drop items whose validator relevance_score is below this.")


@register_function(config_type=BenchmarkExtractorConfig)
async def benchmark_extractor(
    config: BenchmarkExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Scrape benchmark, persist raw + validated JSON, return validated path."""

    async def collect(raw_input: str) -> str:
        product, run_id = parse_collect_input(raw_input)
        raw_file = raw_path(run_id, product, SOURCE_NAME)
        validated_file = validated_path(run_id, product, SOURCE_NAME)

        scrape_input = ScrapeInput(
            query=product,
            limit=config.limit,
            extra={"comment_limit": config.comment_limit}
        )
        result = await asyncio.to_thread(_scrape_benchmark, scrape_input)
        write_json(raw_file, result.model_dump())

        if result.ok and result.items:
            client_config = ClientConfig(
                url=config.validator_url,
                timeout_seconds=config.validator_timeout_seconds,
                max_text_chars=config.validator_max_text_chars,
                min_relevance_score=config.validator_min_relevance_score,
            )
            vresult = await asyncio.to_thread(
                validate_items, client_config, product, result.items
            )
            result.items = vresult.items
            if vresult.status not in ("ok", "no_data"):
                result.error = (
                    f"validator={vresult.status}; "
                    f"kept={vresult.kept}/{vresult.total}; {vresult.note}"
                )

        write_json(validated_file, result.model_dump())
        return str(validated_file)

    yield FunctionInfo.from_fn(
        fn=collect,
        description=(
            "Scrape benchmark for an AI product, validate via validator_core, persist "
            "both raw and validated JSON under runs/{run_id}/, return validated path."
        ),
    )
