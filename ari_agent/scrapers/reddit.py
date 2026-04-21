"""Reddit scraper using the unauthenticated `.json` fallback.

Why `.json` fallback: Reddit OAuth new-app creation is blocked since 2025-11
(Responsible Builder Policy). The `.json` endpoint remains publicly accessible
at ~100 req/10min without auth.

User-Agent is REQUIRED by Reddit policy. Rate-limit: respect `x-ratelimit-*`
headers when present.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from ari_agent.schemas import EvidenceItem, ScrapeInput, ScrapeResult
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

DEFAULT_SUBREDDITS = ["LocalLLaMA", "MachineLearning", "singularity", "ClaudeAI"]


def _search_reddit(query: str, subreddits: list[str], limit: int) -> list[dict]:
    """Hit r/<sub>/search.json for each subreddit and merge."""
    results: list[dict] = []
    for sub in subreddits:
        params = {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "limit": min(limit, 25),
            "raw_json": 1,
        }
        url = f"https://old.reddit.com/r/{sub}/search.json?{urlencode(params)}"
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            continue
        children = resp.json().get("data", {}).get("children", [])
        results.extend(c.get("data", {}) for c in children)
    # Dedup by id and trim
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        rid = r.get("id")
        if rid and rid not in seen:
            seen.add(rid)
            unique.append(r)
        if len(unique) >= limit:
            break
    return unique


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Search Reddit for the query across default subreddits (overridable via extra.subreddits)."""
    subs = input_.extra.get("subreddits") or DEFAULT_SUBREDDITS
    with Timer() as t:
        try:
            raw = _search_reddit(input_.query, subs, input_.limit)
            items = []
            for r in raw:
                created = r.get("created_utc")
                ts = (
                    datetime.fromtimestamp(created, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    if created
                    else None
                )
                items.append(
                    EvidenceItem(
                        source="reddit",
                        source_detail=f"r/{r.get('subreddit', 'unknown')}",
                        url=f"https://reddit.com{r.get('permalink', '')}",
                        author=r.get("author"),
                        title=r.get("title"),
                        text=(r.get("selftext") or "")[:2000],
                        timestamp=ts,
                        score=r.get("score"),
                        metadata={
                            "num_comments": r.get("num_comments"),
                            "upvote_ratio": r.get("upvote_ratio"),
                            "link_flair_text": r.get("link_flair_text"),
                        },
                    )
                )
            return ScrapeResult(source="reddit", ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="reddit", ok=False, error=f"{type(e).__name__}: {e}", latency_ms=t.elapsed_ms
            )
