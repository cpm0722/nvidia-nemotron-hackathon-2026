"""NAT function group: OpenAI blog scraper exposed as a search_posts tool."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_openai.scraper import scrape as _scrape_openai


class OpenAIScraperConfig(FunctionGroupBaseConfig, name="openai_scraper"):
    """OpenAI blog scraper function group configuration."""

    default_limit: int = Field(default=10, ge=1, le=50)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    include: list[str] = Field(default_factory=lambda: ["search_posts"])


@register_function_group(config_type=OpenAIScraperConfig)
async def openai_scraper_group(
    config: OpenAIScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """Create the OpenAI blog scraper function group."""
    group = FunctionGroup(config=config)

    async def search_posts(keyword: str = "") -> str:
        """Fetch OpenAI official blog posts (openai.com/news) and filter by keyword.

        Filters client-side by case-insensitive substring on title + summary.
        An empty keyword returns the latest posts regardless of topic.

        Args:
            keyword: AI product / topic keyword (e.g. "GPT-5", "Codex", "Sora").

        Returns:
            ScrapeResult JSON string with {source, ok, items[], error, latency_ms}.
        """
        result = await run_scraper_async(
            _scrape_openai,
            query=keyword,
            limit=config.default_limit,
            extra={"max_text_chars": config.max_text_chars},
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(name="search_posts", fn=search_posts, description=search_posts.__doc__)
    yield group
