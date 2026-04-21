"""GeekNews (news.hada.io) scraper.

Pipeline:
1. Fetch RSS feed (via feedburner — direct news.hada.io RSS is CloudFront UA-blocked).
2. For each entry, optionally fetch the news.hada.io topic page in parallel and extract:
   - upvote points: <span id='tp{topic_id}'>N</span>
   - comment count: JSON-LD "commentCount": N (omitted when 0 → default to 0)
   - comment bodies: <div class=comment_row id=cid...> ... <span id='contents{cid}' class='comment_contents'>BODY</span>
3. Fall back to RSS-only metadata if HTML fetch fails — keep demo stable.

Selectors confirmed against https://news.hada.io/topic?id=28750 (2026-04-21).
"""

from __future__ import annotations

import html as _html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urlparse

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

FEED_URL = "http://feeds.feedburner.com/geeknews-feed"
TOPIC_BASE = "https://news.hada.io/topic?id="
SOURCE_TAG = "geeknews"

_RE_COMMENTS_JSON = re.compile(r'"commentCount"\s*:\s*(\d+)')
# <div class=comment_row id=cid55992 data-comment-state-id='55992' ... style=--depth:0>
_RE_COMMENT_OPEN = re.compile(
    r"<div class=comment_row id=cid(?P<cid>\d+)[^>]*style=--depth:(?P<depth>\d+)[^>]*>",
    re.IGNORECASE,
)
# Author inside commentinfo: <a href='/@neo'>GN⁺</a>
_RE_COMMENT_AUTHOR = re.compile(r"<a href='/@[^']+'>([^<]+)</a>")
# Content span: <span id='contents55992' class='comment_contents'>...</span>
_RE_COMMENT_CONTENT = re.compile(
    r"<span id='contents(?P<cid>\d+)' class='comment_contents'>(?P<body>.*?)</span>\s*</div>",
    re.DOTALL,
)
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")


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


def _extract_topic_id(link: str) -> str | None:
    try:
        qs = parse_qs(urlparse(link).query)
        return (qs.get("id") or [None])[0]
    except Exception:  # noqa: BLE001
        return None


def _strip_html(s: str) -> str:
    return _RE_WS.sub(" ", _html.unescape(_RE_TAGS.sub(" ", s))).strip()


def _parse_comments(html: str, *, max_comments: int, max_comment_chars: int) -> list[dict]:
    """Parse comment_row blocks in document order. Returns up to `max_comments` comments."""
    contents: dict[str, str] = {}
    for m in _RE_COMMENT_CONTENT.finditer(html):
        contents[m.group("cid")] = m.group("body")

    results: list[dict] = []
    for m in _RE_COMMENT_OPEN.finditer(html):
        cid = m.group("cid")
        depth = int(m.group("depth"))
        start = m.end()
        next_m = _RE_COMMENT_OPEN.search(html, start)
        segment = html[start : next_m.start() if next_m else start + 2000]
        author_m = _RE_COMMENT_AUTHOR.search(segment)
        body_html = contents.get(cid, "")
        body = _strip_html(body_html)[:max_comment_chars]
        if not body:
            continue
        results.append(
            {
                "cid": cid,
                "author": author_m.group(1) if author_m else None,
                "body": body,
                "depth": depth,
            }
        )
        if len(results) >= max_comments:
            break
    return results


def _fetch_html_enrichment(
    topic_id: str,
    *,
    include_comments: bool,
    max_comments: int,
    max_comment_chars: int,
) -> dict:
    """Return {upvotes, comments_count, comments[]}. Empty dict on any failure."""
    try:
        url = f"{TOPIC_BASE}{topic_id}"
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return {}
        html = resp.text
        out: dict = {}
        m_pts = re.search(rf"<span id='tp{topic_id}'>(\d+)</span>", html)
        if m_pts:
            out["upvotes"] = int(m_pts.group(1))
        m_cm = _RE_COMMENTS_JSON.search(html)
        out["comments_count"] = int(m_cm.group(1)) if m_cm else 0
        if include_comments and out["comments_count"] > 0:
            out["comments"] = _parse_comments(
                html,
                max_comments=max_comments,
                max_comment_chars=max_comment_chars,
            )
        return out
    except Exception:  # noqa: BLE001
        return {}


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Fetch GeekNews RSS, filter by keyword, optionally enrich via HTML."""
    enrich_html = bool(input_.extra.get("enrich_html", True))
    max_workers = int(input_.extra.get("html_workers", 4))
    max_text_chars = int(input_.extra.get("max_text_chars", 8000))
    include_comments = bool(input_.extra.get("include_comments", True))
    max_comments_per_topic = int(input_.extra.get("max_comments_per_topic", 10))
    max_comment_chars = int(input_.extra.get("max_comment_chars", 1500))

    with Timer() as t:
        try:
            parsed = _fetch_feed(FEED_URL)
            q = input_.query.lower().strip()

            candidates: list[tuple[str, str, str, str]] = []
            for entry in parsed.entries[: input_.limit * 3]:
                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "") or ""
                text = f"{title}\n{summary}"
                if q and q not in text.lower():
                    continue
                link = entry.get("link", "")
                topic_id = _extract_topic_id(link) or ""
                candidates.append((topic_id, title, summary, link))
                if len(candidates) >= input_.limit:
                    break

            enrichment: dict[str, dict] = {}
            if enrich_html and candidates:
                topic_ids = [tid for tid, *_ in candidates if tid]
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futures = {
                        ex.submit(
                            _fetch_html_enrichment,
                            tid,
                            include_comments=include_comments,
                            max_comments=max_comments_per_topic,
                            max_comment_chars=max_comment_chars,
                        ): tid
                        for tid in topic_ids
                    }
                    for fut in as_completed(futures):
                        tid = futures[fut]
                        try:
                            enrichment[tid] = fut.result()
                        except Exception:  # noqa: BLE001
                            enrichment[tid] = {}

            items: list[EvidenceItem] = []
            for topic_id, title, summary, link in candidates:
                enriched = enrichment.get(topic_id, {}) if enrich_html else {}
                metadata: dict = {"feed_title": parsed.feed.get("title")}
                if topic_id:
                    metadata["topic_id"] = topic_id
                if "upvotes" in enriched:
                    metadata["upvotes"] = enriched["upvotes"]
                if "comments_count" in enriched:
                    metadata["comments_count"] = enriched["comments_count"]
                if include_comments and "comments" in enriched:
                    metadata["comments"] = enriched["comments"]

                items.append(
                    EvidenceItem(
                        source=SOURCE_TAG,
                        source_detail="news.hada.io",
                        url=link,
                        author=None,
                        title=title,
                        text=summary[:max_text_chars],
                        timestamp=None,  # GeekNews RSS timestamp unreliable
                        score=enriched.get("upvotes"),
                        metadata=metadata,
                    )
                )
            return ScrapeResult(source=SOURCE_TAG, ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source=SOURCE_TAG,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
