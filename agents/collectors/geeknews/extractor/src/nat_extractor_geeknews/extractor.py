"""GeekNews (news.hada.io) scraper — topic-id scan for full-text keyword hits.

Pipeline:
1. Discover the latest topic id via the RSS feed (1 request).
2. Scan a trailing window of topic ids (latest .. latest-scan_depth+1) in parallel
   and substring-match the query against the full topic page text (title + body +
   comments). Normalization collapses non-alphanumerics so `nemotron-3` matches
   `Nemotron 3`, `nemotron3`, etc.
3. For hits, extract:
   - title (from `<h1>` inside `class=topictitle link`)
   - external article url (`class=topicurl` / anchor sibling)
   - body (`id=topic_contents`)
   - upvotes (`<span id='tp{tid}'>N</span>`)
   - comments count (JSON-LD `commentCount`)
   - comments (existing `comment_row` parser)
4. Sort by upvotes desc, truncate to `input.limit`.

RSS title-only substring filtering is insufficient for new/niche product names
that only appear in comments or linked article metadata. Scanning by id covers
that. A bounded depth keeps the request budget predictable.

Selectors confirmed against https://news.hada.io/topic?id=28470 (2026-04-22).
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
_RE_COMMENT_OPEN = re.compile(
    r"<div class=comment_row id=cid(?P<cid>\d+)[^>]*style=--depth:(?P<depth>\d+)[^>]*>",
    re.IGNORECASE,
)
_RE_COMMENT_AUTHOR = re.compile(r"<a href='/@[^']+'>([^<]+)</a>")
_RE_COMMENT_CONTENT = re.compile(
    r"<span id='contents(?P<cid>\d+)' class='comment_contents'>(?P<body>.*?)</span>\s*</div>",
    re.DOTALL,
)
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_NON_ALNUM = re.compile(r"[^0-9a-z가-힣]+")

_RE_TOPIC_TITLE = re.compile(
    r"class='topictitle[^']*'[^>]*>.*?<a[^>]*href='(?P<url>[^']+)'[^>]*><h1>(?P<title>[^<]+)</h1></a>"
    r"\s*(?:<span class=topicurl>\(([^)]+)\)</span>)?",
    re.DOTALL,
)
_RE_TOPIC_BODY = re.compile(
    r"<div[^>]*id='topic_contents'[^>]*>(?P<body>.*?)</div>\s*</div>",
    re.DOTALL,
)
_RE_UPVOTES_TPL = r"<span id='tp{tid}'>(\d+)</span>"
_RE_ID_FROM_LINK = re.compile(r"/topic\?id=(\d+)")


def _normalize(s: str) -> str:
    """Lowercase + collapse non-alphanumeric (ASCII + Hangul) → compact key.

    `nemotron-3`, `Nemotron 3`, `nemotron3`, `Nemotron_3` → `nemotron3`.
    """
    return _RE_NON_ALNUM.sub("", s.lower())


def _strip_html(s: str) -> str:
    return _RE_WS.sub(" ", _html.unescape(_RE_TAGS.sub(" ", s))).strip()


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


def _latest_topic_id(parsed: feedparser.FeedParserDict) -> int | None:
    """Extract the numerically largest topic id from the RSS feed entries."""
    ids: list[int] = []
    for entry in parsed.entries[:10]:
        link = entry.get("link") or ""
        m = _RE_ID_FROM_LINK.search(link)
        if m:
            try:
                ids.append(int(m.group(1)))
            except ValueError:
                continue
    return max(ids) if ids else None


def _parse_comments(html: str, *, max_comments: int, max_comment_chars: int) -> list[dict]:
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


def _fetch_topic(tid: int, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Fetch one topic page. Returns HTML, or None on any failure."""
    try:
        resp = requests.get(
            f"{TOPIC_BASE}{tid}",
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:  # noqa: BLE001
        return None


def _match_topic(html: str, q_norm: str) -> bool:
    """True if the normalized query appears anywhere in the topic page text."""
    # Strip tags once, then normalize — prevents false hits on attribute values
    # (e.g. related-topic-id=N) and HTML boilerplate.
    text = _strip_html(html)
    return q_norm in _normalize(text)


def _extract_topic_fields(
    tid: int,
    html: str,
    *,
    include_comments: bool,
    max_comments: int,
    max_comment_chars: int,
    max_text_chars: int,
) -> dict:
    out: dict = {"topic_id": str(tid)}

    m = _RE_TOPIC_TITLE.search(html)
    if m:
        out["external_url"] = m.group("url")
        out["title"] = _html.unescape(m.group("title")).strip()
        out["site"] = (m.group(3) or "").strip() or None
    else:
        out["title"] = ""
        out["external_url"] = f"{TOPIC_BASE}{tid}"

    m = _RE_TOPIC_BODY.search(html)
    if m:
        body_txt = _strip_html(m.group("body"))
        out["body"] = body_txt[:max_text_chars]
    else:
        out["body"] = ""

    m_pts = re.search(_RE_UPVOTES_TPL.format(tid=tid), html)
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


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Scan recent topic ids for full-text query hits; enrich with body + comments."""
    max_text_chars = int(input_.extra.get("max_text_chars", 8000))
    include_comments = bool(input_.extra.get("include_comments", True))
    max_comments_per_topic = int(input_.extra.get("max_comments_per_topic", 10))
    max_comment_chars = int(input_.extra.get("max_comment_chars", 1500))
    scan_depth = int(input_.extra.get("scan_depth", 300))
    scan_workers = int(input_.extra.get("scan_workers", 20))
    rss_fallback_limit = int(input_.extra.get("rss_fallback_limit", 50))

    q = (input_.query or "").strip()
    q_norm = _normalize(q)

    with Timer() as t:
        try:
            parsed = _fetch_feed(FEED_URL)
            latest = _latest_topic_id(parsed)

            # Degenerate cases: empty query OR no latest id.
            # Fall back to RSS recent-N so we never return silent zero.
            if not q_norm or latest is None or scan_depth <= 0:
                return _scrape_rss_fallback(
                    parsed, q=q, q_norm=q_norm,
                    limit=input_.limit,
                    max_text_chars=max_text_chars,
                    include_comments=include_comments,
                    max_comments=max_comments_per_topic,
                    max_comment_chars=max_comment_chars,
                    elapsed=t,
                    rss_limit=rss_fallback_limit,
                )

            start_tid = max(1, latest - scan_depth + 1)
            candidate_ids = list(range(latest, start_tid - 1, -1))

            # Phase 1: parallel fetch + substring match, collect hits (id, html)
            hits: list[tuple[int, str]] = []
            with ThreadPoolExecutor(max_workers=scan_workers) as ex:
                futures = {ex.submit(_fetch_topic, tid): tid for tid in candidate_ids}
                for fut in as_completed(futures):
                    tid = futures[fut]
                    try:
                        html = fut.result()
                    except Exception:  # noqa: BLE001
                        continue
                    if not html:
                        continue
                    if _match_topic(html, q_norm):
                        hits.append((tid, html))

            if not hits:
                # Safety net: try RSS (title+summary) so the surface isn't 0 on
                # products that happen to show up in feed titles this window.
                return _scrape_rss_fallback(
                    parsed, q=q, q_norm=q_norm,
                    limit=input_.limit,
                    max_text_chars=max_text_chars,
                    include_comments=include_comments,
                    max_comments=max_comments_per_topic,
                    max_comment_chars=max_comment_chars,
                    elapsed=t,
                    rss_limit=rss_fallback_limit,
                )

            # Phase 2: extract fields for each hit
            items: list[EvidenceItem] = []
            for tid, html in hits:
                fields = _extract_topic_fields(
                    tid, html,
                    include_comments=include_comments,
                    max_comments=max_comments_per_topic,
                    max_comment_chars=max_comment_chars,
                    max_text_chars=max_text_chars,
                )
                metadata: dict = {
                    "feed_title": parsed.feed.get("title"),
                    "topic_id": str(tid),
                    "topic_url": f"{TOPIC_BASE}{tid}",
                    "comments_count": fields.get("comments_count", 0),
                    "discovery": "id_scan",
                }
                if fields.get("site"):
                    metadata["site"] = fields["site"]
                if "upvotes" in fields:
                    metadata["upvotes"] = fields["upvotes"]
                if include_comments and fields.get("comments"):
                    metadata["comments"] = fields["comments"]

                items.append(
                    EvidenceItem(
                        source=SOURCE_TAG,
                        source_detail="news.hada.io",
                        url=fields["external_url"],
                        author=None,
                        title=fields["title"],
                        text=fields.get("body") or fields.get("title") or "",
                        timestamp=None,  # RSS window alignment is best-effort; skip
                        score=fields.get("upvotes"),
                        metadata=metadata,
                    )
                )

            # Rank: upvotes desc, tiebreak by recency (higher id first)
            items.sort(key=lambda it: (-(it.score or 0), -int(it.metadata["topic_id"])))
            items = items[: input_.limit]

            return ScrapeResult(source=SOURCE_TAG, ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source=SOURCE_TAG,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )


def _scrape_rss_fallback(
    parsed: feedparser.FeedParserDict,
    *,
    q: str,
    q_norm: str,
    limit: int,
    max_text_chars: int,
    include_comments: bool,
    max_comments: int,
    max_comment_chars: int,
    elapsed: Timer,
    rss_limit: int,
) -> ScrapeResult:
    """Legacy title+summary RSS filter. Used when id-scan yields nothing or is disabled."""
    candidates: list[tuple[str, str, str, str]] = []
    for entry in parsed.entries[:rss_limit]:
        title = entry.get("title", "")
        summary = entry.get("summary", "") or entry.get("description", "") or ""
        hay = _normalize(f"{title}\n{summary}")
        if q_norm and q_norm not in hay:
            continue
        link = entry.get("link", "")
        m = _RE_ID_FROM_LINK.search(link)
        topic_id = m.group(1) if m else ""
        candidates.append((topic_id, title, summary, link))
        if len(candidates) >= limit:
            break

    items: list[EvidenceItem] = []
    for topic_id, title, summary, link in candidates:
        metadata: dict = {
            "feed_title": parsed.feed.get("title"),
            "topic_id": topic_id,
            "discovery": "rss_fallback",
        }
        if topic_id:
            html = _fetch_topic(int(topic_id))
            if html:
                fields = _extract_topic_fields(
                    int(topic_id), html,
                    include_comments=include_comments,
                    max_comments=max_comments,
                    max_comment_chars=max_comment_chars,
                    max_text_chars=max_text_chars,
                )
                if fields.get("site"):
                    metadata["site"] = fields["site"]
                if "upvotes" in fields:
                    metadata["upvotes"] = fields["upvotes"]
                metadata["comments_count"] = fields.get("comments_count", 0)
                if include_comments and fields.get("comments"):
                    metadata["comments"] = fields["comments"]
                body = fields.get("body") or summary[:max_text_chars]
                score = fields.get("upvotes")
            else:
                body = summary[:max_text_chars]
                score = None
        else:
            body = summary[:max_text_chars]
            score = None

        items.append(
            EvidenceItem(
                source=SOURCE_TAG,
                source_detail="news.hada.io",
                url=link,
                author=None,
                title=title,
                text=body or title or "",
                timestamp=None,
                score=score,
                metadata=metadata,
            )
        )
    return ScrapeResult(source=SOURCE_TAG, ok=True, items=items, latency_ms=elapsed.elapsed_ms)
