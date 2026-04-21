"""Generic RSS/Atom scraper.

Used for official blogs (OpenAI, DeepMind, Anthropic community, Simon Willison,
Latent Space, etc.) and Korean sources (GeekNews, Kakao Enterprise).

Query filtering is applied client-side (case-insensitive substring match across
title + summary) so the same module handles all feed URLs uniformly.
"""

from __future__ import annotations

import feedparser
import requests

from ari_agent.schemas import EvidenceItem, ScrapeInput, ScrapeResult
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

# Preset feeds the workflow may pick from. Agent can also pass a custom url via extra.feed_url.
FEED_REGISTRY: dict[str, str] = {
    "openai": "https://openai.com/news/rss.xml",
    "deepmind": "https://deepmind.google/blog/rss.xml",
    "latent_space": "https://www.latent.space/feed",
    "simon_willison": "https://simonwillison.net/atom/everything/",
    "sebastian_raschka": "https://magazine.sebastianraschka.com/feed",
    "lilian_weng": "https://lilianweng.github.io/index.xml",
    "techcrunch_ai": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "lobsters": "https://lobste.rs/rss",
    "gary_marcus": "https://garymarcus.substack.com/feed",
    "import_ai": "https://importai.substack.com/feed",
    "ai_snake_oil": "https://www.normaltech.ai/feed",
    "alignment_forum": "https://www.alignmentforum.org/feed.xml",
    "ben_recht": "https://bounded-regret.ghost.io/rss/",
    "geeknews": "http://feeds.feedburner.com/geeknews-feed",  # news.hada.io/rss/news redirects here; direct URL avoids CloudFront UA block
    "kakao_enterprise": "https://kakaoenterprise.github.io/feed.xml",
}


def _fetch_feed(url: str) -> feedparser.FeedParserDict:
    # feedparser doesn't set User-Agent reliably — fetch with requests first for polite headers.
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, */*"},
        timeout=DEFAULT_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Fetch one RSS feed (from registry key or explicit URL) and filter by query substring."""
    feed_key = input_.extra.get("feed_key")
    feed_url = input_.extra.get("feed_url") or (FEED_REGISTRY.get(feed_key) if feed_key else None)
    if not feed_url:
        return ScrapeResult(
            source="rss",
            ok=False,
            error="extra.feed_key or extra.feed_url is required",
            latency_ms=0,
        )

    with Timer() as t:
        try:
            parsed = _fetch_feed(feed_url)
            q = input_.query.lower().strip()
            items: list[EvidenceItem] = []
            for entry in parsed.entries[: input_.limit * 3]:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "") or ""
                text = f"{title}\n{summary}"
                if q and q not in text.lower():
                    continue
                items.append(
                    EvidenceItem(
                        source="rss",
                        source_detail=feed_key or feed_url,
                        url=entry.get("link", feed_url),
                        author=entry.get("author"),
                        title=title,
                        text=summary[:2000],
                        timestamp=entry.get("published") or entry.get("updated"),
                        score=None,
                        metadata={"feed_title": parsed.feed.get("title")},
                    )
                )
                if len(items) >= input_.limit:
                    break
            return ScrapeResult(source="rss", ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="rss",
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
