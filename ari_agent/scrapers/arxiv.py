"""arXiv API scraper — primary-source research signal.

Endpoint: https://export.arxiv.org/api/query (no auth, 1 req / 3 sec).
Returns Atom XML; we parse via feedparser for consistency with RSS scraper.
"""

from __future__ import annotations

import time

import feedparser
import requests

from ari_agent.schemas import EvidenceItem, ScrapeInput, ScrapeResult
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

API_ROOT = "https://export.arxiv.org/api/query"
_last_request_ts = 0.0  # module-level throttle (1 req / 3 sec per arXiv ToS)
MIN_INTERVAL_SECONDS = 3.0


def _throttle() -> None:
    global _last_request_ts
    elapsed = time.perf_counter() - _last_request_ts
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_request_ts = time.perf_counter()


def _query(q: str, limit: int) -> feedparser.FeedParserDict:
    _throttle()
    params = {
        "search_query": f"all:{q}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": min(limit, 50),
    }
    resp = requests.get(
        API_ROOT,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def scrape(input_: ScrapeInput) -> ScrapeResult:
    with Timer() as t:
        try:
            parsed = _query(input_.query, input_.limit)
            items: list[EvidenceItem] = []
            for entry in parsed.entries[: input_.limit]:
                authors = ", ".join(a.get("name", "") for a in (entry.get("authors") or []))
                items.append(
                    EvidenceItem(
                        source="arxiv",
                        source_detail="arxiv.org",
                        url=entry.get("link", ""),
                        author=authors or None,
                        title=entry.get("title", "").replace("\n", " ").strip(),
                        text=(entry.get("summary", "") or "")[:2000],
                        timestamp=entry.get("published") or entry.get("updated"),
                        score=None,
                        metadata={
                            "arxiv_id": (entry.get("id") or "").rsplit("/", 1)[-1],
                            "categories": [t.get("term") for t in (entry.get("tags") or [])],
                        },
                    )
                )
            return ScrapeResult(source="arxiv", ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="arxiv", ok=False, error=f"{type(e).__name__}: {e}", latency_ms=t.elapsed_ms
            )
