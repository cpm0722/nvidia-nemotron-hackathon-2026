"""NAT workflow: arcalive collector — scrape then keyword-validate, no LLM."""

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

from nat_collector_arcalive.extractor import scrape as _scrape_arcalive
from nat_collector_arcalive.validator import filter_items


class ArcaliveCollectorConfig(FunctionBaseConfig, name="arcalive_collector"):
    """arca.live collector 설정 (scrape → keyword validate 순차 실행).

    Args:
        board: 검색할 arca.live 채널 슬러그 (e.g. "alpaca", "aiservice").
        max_pages: 검색 결과 최대 페이지 수.
        limit: 반환할 최대 게시글 수.
    """

    board: str = Field(default="alpaca", description="Arcalive channel slug to search")
    max_pages: int = Field(default=2, description="Maximum search result pages to crawl")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum posts to return")


@register_function(config_type=ArcaliveCollectorConfig)
async def arcalive_collector(
    config: ArcaliveCollectorConfig, _builder: Builder
) -> AsyncGenerator[FunctionInfo, None]:
    """단일 함수 workflow: product_name을 받아 scrape→validate→ScrapeResult JSON 반환.

    Args:
        config: board / max_pages / limit 설정.
        _builder: NAT workflow builder (미사용).

    Yields:
        FunctionInfo wrapping the collect function.
    """

    async def collect(product_name: str) -> str:
        inp = ScrapeInput(
            query=product_name,
            limit=config.limit,
            extra={"board": config.board, "max_pages": config.max_pages},
        )
        result = await asyncio.to_thread(_scrape_arcalive, inp)
        if result.ok:
            result.items = filter_items(result.items, product_name)
        return json.dumps(result.model_dump(), ensure_ascii=False, default=str)

    yield FunctionInfo.from_fn(
        fn=collect,
        description="Collect arca.live posts about an AI product and filter by keyword relevance.",
    )
