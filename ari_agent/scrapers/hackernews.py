"""HackerNews scraper using Algolia search API (most practical for keyword queries).

Algolia: https://hn.algolia.com/api
Firebase: https://hacker-news.firebaseio.com/v0 (used for single-item lookup only)

Both endpoints are public and require no auth.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from ari_agent.schemas import EvidenceItem, ScrapeInput, ScrapeResult
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

ALGOLIA = "https://hn.algolia.com/api/v1/search"


def _search(query: str, limit: int, since_days: int) -> list[dict]:
    # tags: story,comment. numericFilters filters by created_at_i (unix seconds).
    since_unix = int(datetime.now(tz=timezone.utc).timestamp()) - since_days * 86400
    params = {
        "query": query,
        "tags": "(story,comment)",
        "hitsPerPage": min(limit, 50),
        "numericFilters": f"created_at_i>{since_unix}",
    }
    resp = requests.get(
        ALGOLIA,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json().get("hits", [])


def scrape(input_: ScrapeInput) -> ScrapeResult:
    with Timer() as t:
        try:
            raw = _search(input_.query, input_.limit, input_.since_days)
            items = []
            for h in raw:
                hid = h.get("objectID")
                url = h.get("url") or f"https://news.ycombinator.com/item?id={hid}"
                items.append(
                    EvidenceItem(
                        source="hackernews",
                        source_detail="algolia",
                        url=url,
                        author=h.get("author"),
                        title=h.get("title") or h.get("story_title"),
                        text=(h.get("comment_text") or h.get("story_text") or "")[:2000],
                        timestamp=h.get("created_at"),
                        score=h.get("points"),
                        metadata={
                            "num_comments": h.get("num_comments"),
                            "story_id": h.get("story_id"),
                            "tags": h.get("_tags"),
                        },
                    )
                )
            return ScrapeResult(source="hackernews", ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="hackernews",
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
