"""NAT workflow: reddit extractor — scrape, write raw file, validate, write validated file.

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

from nat_extractor_reddit.extractor import scrape as _scrape_reddit

SOURCE_NAME = "reddit"


class RedditExtractorConfig(FunctionBaseConfig, name="reddit_extractor"):
    """Reddit extractor 설정 (scrape → write raw → validator A2A → write validated)."""

    subreddits: list[str] = Field(
        default_factory=lambda: ["LocalLLaMA", "MachineLearning", "ClaudeAI", "singularity"]
    )
    limit: int = Field(default=10, ge=1, le=100)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    include_comments: bool = Field(default=True)
    max_comments_per_post: int = Field(default=5, ge=0, le=30)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    comment_workers: int = Field(default=3, ge=1, le=6)
    validator_url: str = Field(default="http://localhost:10026")
    validator_timeout_seconds: int = Field(default=120, ge=10, le=600)


@register_function(config_type=RedditExtractorConfig)
async def reddit_extractor(
    config: RedditExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """Scrape Reddit, persist raw + validated JSON files, return validated path."""

    async def collect(raw_input: str) -> str:
        product, run_id = parse_collect_input(raw_input)
        raw_file = raw_path(run_id, product, SOURCE_NAME)
        validated_file = validated_path(run_id, product, SOURCE_NAME)

        scrape_input = ScrapeInput(
            query=product,
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
            "Scrape Reddit for an AI product, validate via validator A2A, persist both "
            "raw and validated JSON under runs/{run_id}/, and return the validated file path."
        ),
    )
