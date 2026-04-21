"""OpenAI official blog scraper via RSS (openai.com/news/rss.xml).

Single-feed specialization — filters client-side by case-insensitive substring on
title + summary. Empty query returns the latest posts regardless of topic.
"""

from __future__ import annotations

import feedparser
import requests

from ari_core import (
    DEFAULT_TIMEOUT_SECONDS,
    USER_AGENT,
    EvidenceItem,
    ScrapeInput,
    ScrapeResult,
    Timer,
)

FEED_URL = "https://openai.com/news/rss.xml"
SOURCE_TAG = "openai"


def _fetch_feed(url: str) -> feedparser.FeedParserDict:
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, */*",
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def scrape(input_: ScrapeInput) -> ScrapeResult:
    max_text_chars = int(input_.extra.get("max_text_chars", 8000))
    with Timer() as t:
        try:
            parsed = _fetch_feed(FEED_URL)
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
                        source=SOURCE_TAG,
                        source_detail="openai.com/news",
                        url=entry.get("link", FEED_URL),
                        author=entry.get("author"),
                        title=title,
                        text=summary[:max_text_chars],
                        timestamp=entry.get("published") or entry.get("updated"),
                        score=None,
                        metadata={"feed_title": parsed.feed.get("title")},
                    )
                )
                if len(items) >= input_.limit:
                    break
            return ScrapeResult(source=SOURCE_TAG, ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source=SOURCE_TAG,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
