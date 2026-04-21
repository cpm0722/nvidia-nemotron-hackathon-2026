"""NAT function group: GeekNews scraper exposed as a search_posts tool."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_geeknews.scraper import scrape as _scrape_geeknews


class GeekNewsScraperConfig(FunctionGroupBaseConfig, name="geeknews_scraper"):
    """GeekNews scraper function group configuration.

    Args:
        default_limit: Maximum posts to return.
        max_text_chars: Truncate each summary to this length.
        enrich_html: Fetch news.hada.io topic pages for upvote / comment counts + comment bodies.
        include_comments: Include parsed comments in metadata.comments.
        max_comments_per_topic: Cap comments per topic.
        max_comment_chars: Truncate each comment body to this length.
        html_workers: Parallel worker count for HTML enrichment.
        include: NAT-exposed function names.
    """

    default_limit: int = Field(default=10, ge=1, le=30)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    enrich_html: bool = Field(default=True)
    include_comments: bool = Field(default=True)
    max_comments_per_topic: int = Field(default=10, ge=0, le=50)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    html_workers: int = Field(default=4, ge=1, le=8)
    include: list[str] = Field(default_factory=lambda: ["search_posts"])


@register_function_group(config_type=GeekNewsScraperConfig)
async def geeknews_scraper_group(
    config: GeekNewsScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """Create the GeekNews scraper function group."""
    group = FunctionGroup(config=config)

    async def search_posts(keyword: str = "") -> str:
        """Fetch GeekNews (news.hada.io) posts — Korean tech community reactions.

        Returns title, summary, URL, plus metadata.upvotes, metadata.comments_count,
        and metadata.comments (list of {cid, author, body, depth}) when enrich_html
        is enabled. Pass the keyword in Korean or English; empty keyword returns
        the latest posts.

        Args:
            keyword: AI product / topic keyword (e.g. "Claude", "Nemotron", "클로드").

        Returns:
            ScrapeResult JSON string with {source, ok, items[], error, latency_ms}.
        """
        extra = {
            "enrich_html": config.enrich_html,
            "html_workers": config.html_workers,
            "max_text_chars": config.max_text_chars,
            "include_comments": config.include_comments,
            "max_comments_per_topic": config.max_comments_per_topic,
            "max_comment_chars": config.max_comment_chars,
        }
        result = await run_scraper_async(
            _scrape_geeknews,
            query=keyword,
            limit=config.default_limit,
            extra=extra,
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(name="search_posts", fn=search_posts, description=search_posts.__doc__)
    yield group
