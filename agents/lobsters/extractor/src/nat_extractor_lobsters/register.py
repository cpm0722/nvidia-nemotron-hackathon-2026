"""NAT function group: Lobsters scraper exposed as a search_posts tool."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_lobsters.scraper import scrape as _scrape_lobsters


class LobstersScraperConfig(FunctionGroupBaseConfig, name="lobsters_scraper"):
    """Lobsters scraper function group configuration.

    Args:
        default_limit: Maximum posts to return.
        max_text_chars: Truncate each story body to this length.
        enrich_json: Fetch per-story JSON for richer body + score + comments.
        include_comments: Include top comments in metadata.comments.
        max_comments_per_story: Cap top comments per story.
        max_comment_chars: Truncate each comment body to this length.
        workers: Parallel worker count for JSON enrichment.
        include: NAT-exposed function names.
    """

    default_limit: int = Field(default=10, ge=1, le=50)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    enrich_json: bool = Field(default=True)
    include_comments: bool = Field(default=True)
    max_comments_per_story: int = Field(default=10, ge=0, le=50)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    workers: int = Field(default=4, ge=1, le=8)
    include: list[str] = Field(default_factory=lambda: ["search_posts"])


@register_function_group(config_type=LobstersScraperConfig)
async def lobsters_scraper_group(
    config: LobstersScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """Create the Lobsters scraper function group."""
    group = FunctionGroup(config=config)

    async def search_posts(keyword: str = "") -> str:
        """Fetch Lobsters (lobste.rs) tech discussion posts and filter by keyword.

        Each item includes: story body (description_plain), tags, score,
        comments_count, and top comments (author, body, score, depth) via the
        /s/{id}.json API. An empty keyword returns the most recent posts.

        Args:
            keyword: AI product / topic keyword (e.g. "Claude", "LLM", "agents").

        Returns:
            ScrapeResult JSON string with {source, ok, items[], error, latency_ms}.
        """
        extra = {
            "max_text_chars": config.max_text_chars,
            "enrich_json": config.enrich_json,
            "include_comments": config.include_comments,
            "max_comments_per_story": config.max_comments_per_story,
            "max_comment_chars": config.max_comment_chars,
            "workers": config.workers,
        }
        result = await run_scraper_async(
            _scrape_lobsters,
            query=keyword,
            limit=config.default_limit,
            extra=extra,
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(name="search_posts", fn=search_posts, description=search_posts.__doc__)
    yield group
