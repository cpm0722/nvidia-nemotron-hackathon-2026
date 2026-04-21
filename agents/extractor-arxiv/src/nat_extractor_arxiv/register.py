"""NAT function group: arXiv scraper exposed as a search_papers tool."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_arxiv.scraper import scrape as _scrape_arxiv


class ArxivScraperConfig(FunctionGroupBaseConfig, name="arxiv_scraper"):
    """arXiv scraper function group configuration.

    Args:
        default_limit: Maximum papers to return.
        max_text_chars: Truncate each abstract to this length.
        include: NAT-exposed function names.
    """

    default_limit: int = Field(default=10, ge=1, le=50)
    max_text_chars: int = Field(default=8000, ge=500, le=40000)
    include: list[str] = Field(default_factory=lambda: ["search_papers"])


@register_function_group(config_type=ArxivScraperConfig)
async def arxiv_scraper_group(
    config: ArxivScraperConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """Create the arXiv scraper function group with a single search_papers tool."""
    group = FunctionGroup(config=config)

    async def search_papers(keyword: str) -> str:
        """Search arXiv for papers matching a model name or research keyword.

        Returns the most recent N papers sorted by submittedDate (descending).
        Each item includes title, abstract, authors, arXiv ID, categories.
        Throttled to 1 request / 3 seconds per arXiv ToS.

        Args:
            keyword: Model name or topic keyword (e.g. "Nemotron", "Claude", "MoE routing").

        Returns:
            ScrapeResult JSON string with {source, ok, items[], error, latency_ms}.
        """
        result = await run_scraper_async(
            _scrape_arxiv,
            query=keyword,
            limit=config.default_limit,
            extra={"max_text_chars": config.max_text_chars},
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(name="search_papers", fn=search_papers, description=search_papers.__doc__)
    yield group
