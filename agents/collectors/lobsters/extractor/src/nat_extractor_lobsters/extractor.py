"""Lobsters (lobste.rs) tech discussion scraper.

Two-stage pipeline:
1. RSS for the feed list (title, tags, external URL).
2. Per-story JSON API (`https://lobste.rs/s/{short_id}.json`) for richer body
   (description_plain) and top comments (author, body, score, depth).

Stage 2 is parallel and optional (disable with `enrich_json=False`).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

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

FEED_URL = "https://lobste.rs/rss"
SOURCE_TAG = "lobsters"

_RE_SHORT_ID = re.compile(r"lobste\.rs/s/([A-Za-z0-9]+)")


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


def _extract_tags(entry) -> list[str]:  # noqa: ANN001
    out: list[str] = []
    for t in (entry.get("tags") or []):
        term = t.get("term") if isinstance(t, dict) else getattr(t, "term", None)
        if term:
            out.append(term)
    return out


def _extract_short_id(entry) -> str | None:  # noqa: ANN001
    """Short ID appears in entry.id or entry.comments (both point at lobste.rs/s/{id})."""
    for candidate in (entry.get("id"), entry.get("comments")):
        if candidate:
            m = _RE_SHORT_ID.search(candidate)
            if m:
                return m.group(1)
    return None


def _fetch_story_json(
    short_id: str,
    *,
    max_comments: int,
    max_comment_chars: int,
    max_text_chars: int,
) -> dict:
    """Return {description_plain, score, comment_count, comments_url, comments[]} or {} on failure."""
    try:
        url = f"https://lobste.rs/s/{short_id}.json"
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return {}
        d = resp.json()
        comments_raw = d.get("comments") or []
        comments: list[dict] = []
        for c in comments_raw[: max_comments * 3]:  # over-fetch; we filter deleted below
            if c.get("is_deleted") or c.get("is_moderated"):
                continue
            body = (c.get("comment_plain") or c.get("comment") or "").strip()
            if not body:
                continue
            user = c.get("commenting_user")
            username = user.get("username") if isinstance(user, dict) else user
            comments.append(
                {
                    "author": username,
                    "body": body[:max_comment_chars],
                    "score": c.get("score"),
                    "depth": c.get("depth", 0),
                }
            )
            if len(comments) >= max_comments:
                break
        return {
            "description_plain": (d.get("description_plain") or "")[:max_text_chars],
            "score": d.get("score"),
            "comment_count": d.get("comment_count"),
            "comments_url": d.get("comments_url"),
            "comments": comments,
        }
    except Exception:  # noqa: BLE001
        return {}


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Fetch Lobsters RSS → optional per-story JSON enrichment (body + comments)."""
    max_text_chars = int(input_.extra.get("max_text_chars", 8000))
    enrich_json = bool(input_.extra.get("enrich_json", True))
    include_comments = bool(input_.extra.get("include_comments", True))
    max_comments_per_story = int(input_.extra.get("max_comments_per_story", 10))
    max_comment_chars = int(input_.extra.get("max_comment_chars", 1500))
    workers = int(input_.extra.get("workers", 4))

    with Timer() as t:
        try:
            parsed = _fetch_feed(FEED_URL)
            q = input_.query.lower().strip()

            candidates: list[tuple[str | None, object]] = []
            for entry in parsed.entries[: input_.limit * 3]:
                title = entry.get("title", "") or ""
                summary = entry.get("summary", "") or entry.get("description", "") or ""
                if q and q not in f"{title}\n{summary}".lower():
                    continue
                short_id = _extract_short_id(entry)
                candidates.append((short_id, entry))
                if len(candidates) >= input_.limit:
                    break

            enrichment: dict[str, dict] = {}
            if enrich_json and candidates:
                ids = [sid for sid, _ in candidates if sid]
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = {
                        ex.submit(
                            _fetch_story_json,
                            sid,
                            max_comments=max_comments_per_story if include_comments else 0,
                            max_comment_chars=max_comment_chars,
                            max_text_chars=max_text_chars,
                        ): sid
                        for sid in ids
                    }
                    for fut in as_completed(futures):
                        sid = futures[fut]
                        try:
                            enrichment[sid] = fut.result()
                        except Exception:  # noqa: BLE001
                            enrichment[sid] = {}

            items: list[EvidenceItem] = []
            for short_id, entry in candidates:
                title = entry.get("title", "") or ""
                summary = entry.get("summary", "") or entry.get("description", "") or ""
                enr = enrichment.get(short_id or "", {})
                body = enr.get("description_plain") or summary[:max_text_chars]
                tags = _extract_tags(entry)
                comments_url = entry.get("comments") or enr.get("comments_url")

                metadata: dict = {
                    "tags": tags,
                    "comments_url": comments_url,
                }
                if short_id:
                    metadata["short_id"] = short_id
                if "comment_count" in enr:
                    metadata["comments_count"] = enr["comment_count"]
                if include_comments and "comments" in enr:
                    metadata["comments"] = enr["comments"]

                items.append(
                    EvidenceItem(
                        source=SOURCE_TAG,
                        source_detail="lobste.rs",
                        url=entry.get("link", FEED_URL),
                        author=entry.get("author"),
                        title=title,
                        text=body,
                        timestamp=entry.get("published") or entry.get("updated"),
                        score=enr.get("score"),
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
