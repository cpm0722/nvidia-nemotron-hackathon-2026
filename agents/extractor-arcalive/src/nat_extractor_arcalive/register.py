"""NAT function group 등록: arca.live 크롤러를 search_posts 툴로 노출한다."""

import asyncio
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from nat_extractor_arcalive.crawler import crawl
from nat_extractor_arcalive.models import CrawlResult


class ArcaliveScraperConfig(FunctionGroupBaseConfig, name="arcalive_scraper"):
    """arca.live 크롤러 function group 설정.

    Args:
        board: 검색할 arca.live 채널 슬러그 (e.g. "aiservice", "alpaca").
        max_pages: 검색 결과 최대 페이지 수.
        include: NAT에 노출할 함수 이름 목록.
    """

    board: str = Field(default="aiservice", description="Arcalive channel slug to search")
    max_pages: int = Field(default=2, description="Maximum search result pages to crawl")
    include: list[str] = Field(default_factory=lambda: ["search_posts"])


@register_function_group(config_type=ArcaliveScraperConfig)
async def arcalive_scraper_group(
    config: ArcaliveScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """arca.live 크롤러 function group을 생성·등록한다.

    search_posts 툴 하나를 노출하며, 동기 크롤러(crawl)를 asyncio.to_thread로 실행해
    이벤트 루프 블로킹을 방지한다.

    Args:
        config: 크롤러 설정 (board, max_pages).
        _builder: 워크플로우 빌더 (미사용).

    Yields:
        FunctionGroup containing the search_posts tool.
    """
    group = FunctionGroup(config=config)

    async def search_posts(product_name: str) -> str:
        """arca.live에서 AI 프러덕트에 대한 사용자 반응 게시글 Top-5를 수집한다.

        검색 결과 중 제목에 product_name이 포함된 게시글만 선별하고,
        댓글 수 → 추천 수 → 최신 순으로 정렬한 Top-5의 본문·댓글·추천수를 반환한다.

        Args:
            product_name: 검색할 AI 프러덕트 이름 (e.g. "GPT-5", "Claude 4", "Gemma 4").

        Returns:
            CrawlResult JSON 문자열 (query, result 필드 포함).
        """
        result: CrawlResult = await asyncio.to_thread(
            crawl, product_name, config.board, config.max_pages
        )
        return result.model_dump_json(indent=2)

    group.add_function(name="search_posts", fn=search_posts, description=search_posts.__doc__)
    yield group
