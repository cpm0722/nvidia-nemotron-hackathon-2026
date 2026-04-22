"""NAT workflow: arcalive extractor — scrape, write raw file, validate, write validated file.

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

from nat_extractor_arcalive.extractor import scrape as _scrape_arcalive

SOURCE_NAME = "arcalive"


class ArcaliveExtractorConfig(FunctionBaseConfig, name="arcalive_extractor"):
    """arca.live extractor 설정 (scrape → write raw → validator A2A → write validated).

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


@register_function(config_type=ArcaliveExtractorConfig)
async def arcalive_extractor(
    config: ArcaliveExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Scrape arca.live, persist raw + validated JSON files, return validated path."""

    async def collect(raw_input: str) -> str:
        product, run_id = parse_collect_input(raw_input)
        raw_file = raw_path(run_id, product, SOURCE_NAME)
        validated_file = validated_path(run_id, product, SOURCE_NAME)

        scrape_input = ScrapeInput(
            query=product,
            limit=config.limit,
            extra={"board": config.board, "max_pages": config.max_pages},
        )
        result = await asyncio.to_thread(_scrape_arcalive, scrape_input)
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
                pass  # fall back to unfiltered items

        write_json(validated_file, result.model_dump())
        return str(validated_file)

    yield FunctionInfo.from_fn(
        fn=collect,
        description=(
            "Scrape arca.live for an AI product, validate items via the validator A2A, "
            "persist both raw and validated JSON under runs/{run_id}/, and return the "
            "validated file path."
        ),
    )
