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


def _search_reddit(query: str, subreddits: list[str], limit: int) -> tuple[list[dict], list[str]]:
    """Hit r/<sub>/search.json for each subreddit and merge.

    Returns (rows, warnings). Warnings contain per-subreddit HTTP status when
    Reddit blocks the request (403/429 are common on cloud IPs) — the caller
    surfaces them in `ScrapeResult.error` so upstream sees *why* a run was empty
    instead of silently getting 0 items.
    """
    results: list[dict] = []
    warnings: list[str] = []
    for sub in subreddits:
        params = {
            "q": query,
            "restrict_sr": "on",
            "sort": "new",
            "limit": min(limit, 25),
            "raw_json": 1,
        }
        url = f"https://old.reddit.com/r/{sub}/search.json?{urlencode(params)}"
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            warnings.append(f"r/{sub}: {type(e).__name__}: {e}")
            continue
        if resp.status_code != 200:
            warnings.append(f"r/{sub}: HTTP {resp.status_code}")
            continue
        try:
            body = resp.json()
        except ValueError as e:
            warnings.append(f"r/{sub}: non-JSON response ({e})")
            continue
        if not isinstance(body, dict):
            warnings.append(f"r/{sub}: unexpected JSON shape {type(body).__name__}")
            continue
        children = ((body.get("data") or {}) if isinstance(body.get("data"), dict) else {}).get("children", [])
        for c in children:
            if not isinstance(c, dict):
                continue
            d = c.get("data")
            if isinstance(d, dict):
                results.append(d)
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
    return unique, warnings


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Search Reddit for the query across default subreddits (overridable via extra.subreddits)."""
    subs = input_.extra.get("subreddits") or DEFAULT_SUBREDDITS
    with Timer() as t:
        try:
            raw, warnings = _search_reddit(input_.query, subs, input_.limit)
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
            # If nothing came back but subreddits returned non-200, surface the reason.
            error: str | None = None
            if not items and warnings:
                error = "; ".join(warnings)
            elif warnings:
                error = f"partial; {'; '.join(warnings)}"
            return ScrapeResult(
                source="reddit",
                ok=bool(items),
                items=items,
                error=error,
                latency_ms=t.elapsed_ms,
            )
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="reddit", ok=False, error=f"{type(e).__name__}: {e}", latency_ms=t.elapsed_ms
            )
