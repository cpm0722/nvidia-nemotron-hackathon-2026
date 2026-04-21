"""Helper for NAT wrappers: run a sync scraper in a thread and return JSON-safe dict."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from ari_core.schemas import ScrapeInput, ScrapeResult


async def run_scraper_async(
    fn: Callable[[ScrapeInput], ScrapeResult],
    *,
    query: str,
    limit: int = 20,
    since_days: int = 30,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Off-load a sync scraper to a thread and return its serialized result."""
    inp = ScrapeInput(query=query, limit=limit, since_days=since_days, extra=extra or {})
    result = await asyncio.to_thread(fn, inp)
    return result.model_dump()
