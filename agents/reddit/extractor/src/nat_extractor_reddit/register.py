"""NAT function group: Reddit scraper exposed as a search_posts tool."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_reddit.scraper import scrape as _scrape_reddit


class RedditScraperConfig(FunctionGroupBaseConfig, name="reddit_scraper"):
    """Reddit scraper function group configuration.

    Args:
        default_subreddits: Subreddit slugs to search by default.
        default_limit: Maximum posts to return.
        max_text_chars: Truncate each post selftext to this length.
        include_comments: Fetch top comments per post (extra HTTP per post).
        max_comments_per_post: Cap top comments per post.
        max_comment_chars: Truncate each comment body to this length.
        comment_workers: Parallel worker count for comment fetching.
        include: NAT-exposed function names.
    """

    default_subreddits: list[str] = Field(
        default_factory=lambda: ["LocalLLaMA", "MachineLearning", "ClaudeAI", "singularity"]
    )
    default_limit: int = Field(default=10, ge=1, le=100)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    include_comments: bool = Field(default=True)
    max_comments_per_post: int = Field(default=5, ge=0, le=30)
    max_comment_chars: int = Field(default=1500, ge=100, le=10000)
    comment_workers: int = Field(default=3, ge=1, le=6)
    include: list[str] = Field(default_factory=lambda: ["search_posts"])


@register_function_group(config_type=RedditScraperConfig)
async def reddit_scraper_group(
    config: RedditScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """Create the Reddit scraper function group.

    Exposes a single `search_posts` tool. The sync scraper runs off the event
    loop via `asyncio.to_thread` inside `run_scraper_async`.

    Args:
        config: Scraper configuration (subreddits, limits, comment toggles).
        _builder: Workflow builder (unused).

    Yields:
        FunctionGroup containing the `search_posts` tool.
    """
    group = FunctionGroup(config=config)

    async def search_posts(product_name: str) -> str:
        """Search Reddit for community reactions to an AI product.

        Hits r/<subreddit>/search.json across the configured default subreddits and
        returns normalized EvidenceItem records. Each item includes the post title,
        selftext, score, num_comments, and (when include_comments is true) top
        comments with author / body / score in metadata.comments.

        Args:
            product_name: AI product keyword (e.g. "Claude Opus 4.7", "GPT-5", "Gemma 4").

        Returns:
            ScrapeResult JSON string with {source, ok, items[], error, latency_ms}.
        """
        extra = {
            "subreddits": config.default_subreddits,
            "max_text_chars": config.max_text_chars,
            "include_comments": config.include_comments,
            "max_comments_per_post": config.max_comments_per_post,
            "max_comment_chars": config.max_comment_chars,
            "comment_workers": config.comment_workers,
        }
        result = await run_scraper_async(
            _scrape_reddit,
            query=product_name,
            limit=config.default_limit,
            extra=extra,
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(name="search_posts", fn=search_posts, description=search_posts.__doc__)
    yield group
