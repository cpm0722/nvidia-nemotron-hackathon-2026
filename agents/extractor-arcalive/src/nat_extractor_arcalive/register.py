"""NAT function group 등록: arca.live 크롤러를 search_posts 툴로 노출한다."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_arcalive.scraper import scrape as _scrape_arcalive


class ArcaliveScraperConfig(FunctionGroupBaseConfig, name="arcalive_scraper"):
    """arca.live 크롤러 function group 설정.

    Args:
        board: 검색할 arca.live 채널 슬러그 (e.g. "aiservice", "alpaca").
        max_pages: 검색 결과 최대 페이지 수.
        default_limit: 반환할 최대 게시글 수.
        include: NAT에 노출할 함수 이름 목록.
    """

    board: str = Field(default="alpaca", description="Arcalive channel slug to search")
    max_pages: int = Field(default=2, description="Maximum search result pages to crawl")
    default_limit: int = Field(default=5, ge=1, le=20, description="Maximum posts to return")
    include: list[str] = Field(default_factory=lambda: ["search_posts"])


@register_function_group(config_type=ArcaliveScraperConfig)
async def arcalive_scraper_group(
    config: ArcaliveScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """arca.live 크롤러 function group을 생성·등록한다.

    search_posts 툴 하나를 노출하며, ari_core의 run_scraper_async를 통해
    동기 스크래퍼를 비동기적으로 실행한다.

    Args:
        config: 크롤러 설정 (board, max_pages, default_limit).
        _builder: 워크플로우 빌더 (미사용).

    Yields:
        FunctionGroup containing the search_posts tool.
    """
    group = FunctionGroup(config=config)

    async def search_posts(product_name: str) -> str:
        """arca.live에서 AI 프러덕트에 대한 사용자 반응 게시글을 수집한다.

        검색 결과 중 제목에 product_name이 포함된 게시글만 선별하고,
        댓글 수 → 추천 수 → 최신 순으로 정렬한 상위 게시글의 본문·댓글·추천수를 반환한다.

        Args:
            product_name: 검색할 AI 프러덕트 이름 (e.g. "GPT-5", "Claude 4", "Gemma 4").

        Returns:
            ScrapeResult JSON 문자열 (source, ok, items[], latency_ms 필드 포함).
        """
        extra = {
            "board": config.board,
            "max_pages": config.max_pages,
        }
        result = await run_scraper_async(
            _scrape_arcalive,
            query=product_name,
            limit=config.default_limit,
            extra=extra,
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(name="search_posts", fn=search_posts, description=search_posts.__doc__)
    yield group
