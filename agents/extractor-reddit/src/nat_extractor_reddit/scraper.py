"""Reddit scraper using the unauthenticated `.json` fallback.

Why `.json` fallback: Reddit OAuth new-app creation is blocked since 2025-11
(Responsible Builder Policy). The `.json` endpoint remains publicly accessible
at ~100 req/10min without auth. User-Agent is REQUIRED by Reddit policy.

Enrichment: optionally fetch top comments per post via `/r/{sub}/comments/{id}.json`
in a small thread pool.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from ari_core import (
    DEFAULT_TIMEOUT_SECONDS,
    USER_AGENT,
    EvidenceItem,
    ScrapeInput,
    ScrapeResult,
    Timer,
)

DEFAULT_SUBREDDITS = ["LocalLLaMA", "MachineLearning", "singularity", "ClaudeAI"]


def _search_reddit(query: str, subreddits: list[str], limit: int) -> tuple[list[dict], list[str]]:
    """Hit r/<sub>/search.json for each subreddit and merge.

    Returns (unique_rows, warnings). Warnings surface HTTP failures.
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
            warnings.append(f"{sub}:network:{type(e).__name__}")
            continue
        if resp.status_code != 200:
            warnings.append(f"{sub}:http_{resp.status_code}")
            continue
        try:
            children = resp.json().get("data", {}).get("children", [])
        except ValueError:
            warnings.append(f"{sub}:invalid_json")
            continue
        results.extend(c.get("data", {}) for c in children if isinstance(c, dict))

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


def _fetch_comments(
    subreddit: str,
    post_id: str,
    *,
    max_comments: int,
    max_comment_chars: int,
) -> list[dict]:
    """Fetch up to `max_comments` top-level comments for one post."""
    url = (
        f"https://old.reddit.com/r/{subreddit}/comments/{post_id}.json"
        f"?raw_json=1&limit={max_comments}&depth=1&sort=top"
    )
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return []
        children = data[1].get("data", {}).get("children", [])
        out: list[dict] = []
        for c in children:
            if c.get("kind") != "t1":
                continue
            cd = c.get("data", {})
            body = (cd.get("body") or "").strip()
            if not body:
                continue
            out.append(
                {
                    "author": cd.get("author"),
                    "body": body[:max_comment_chars],
                    "score": cd.get("score"),
                }
            )
            if len(out) >= max_comments:
                break
        return out
    except Exception:  # noqa: BLE001
        return []


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Search Reddit for `query`; optionally enrich each post with top comments."""
    subs = input_.extra.get("subreddits") or DEFAULT_SUBREDDITS
    max_text_chars = int(input_.extra.get("max_text_chars", 8000))
    include_comments = bool(input_.extra.get("include_comments", True))
    max_comments_per_post = int(input_.extra.get("max_comments_per_post", 5))
    max_comment_chars = int(input_.extra.get("max_comment_chars", 1500))
    comment_workers = int(input_.extra.get("comment_workers", 3))

    with Timer() as t:
        try:
            raw, warnings = _search_reddit(input_.query, subs, input_.limit)

            base_items: list[tuple[dict, EvidenceItem]] = []
            for r in raw:
                created = r.get("created_utc")
                ts = (
                    datetime.fromtimestamp(created, tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                    if created
                    else None
                )
                item = EvidenceItem(
                    source="reddit",
                    source_detail=f"r/{r.get('subreddit', 'unknown')}",
                    url=f"https://reddit.com{r.get('permalink', '')}",
                    author=r.get("author"),
                    title=r.get("title"),
                    text=(r.get("selftext") or "")[:max_text_chars],
                    timestamp=ts,
                    score=r.get("score"),
                    metadata={
                        "num_comments": r.get("num_comments"),
                        "upvote_ratio": r.get("upvote_ratio"),
                        "link_flair_text": r.get("link_flair_text"),
                    },
                )
                base_items.append((r, item))

            if include_comments and base_items:
                jobs = [
                    (r.get("subreddit", ""), r.get("id", ""), idx)
                    for idx, (r, _) in enumerate(base_items)
                    if r.get("id") and r.get("subreddit") and (r.get("num_comments") or 0) > 0
                ]
                if jobs:
                    with ThreadPoolExecutor(max_workers=comment_workers) as ex:
                        futures = {
                            ex.submit(
                                _fetch_comments,
                                sub,
                                pid,
                                max_comments=max_comments_per_post,
                                max_comment_chars=max_comment_chars,
                            ): idx
                            for sub, pid, idx in jobs
                        }
                        for fut in as_completed(futures):
                            idx = futures[fut]
                            try:
                                base_items[idx][1].metadata["comments"] = fut.result()
                            except Exception:  # noqa: BLE001
                                base_items[idx][1].metadata["comments"] = []

            items = [it for _, it in base_items]
            ok = bool(items) or not warnings
            err = None
            if warnings and not items:
                err = "all subreddits failed: " + "; ".join(warnings)
            elif warnings:
                err = "partial: " + "; ".join(warnings)
            return ScrapeResult(
                source="reddit",
                ok=ok,
                items=items,
                error=err,
                latency_ms=t.elapsed_ms,
            )
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="reddit",
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
