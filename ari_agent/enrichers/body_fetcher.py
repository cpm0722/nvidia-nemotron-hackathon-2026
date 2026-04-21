"""Body Enricher — fetches each evidence URL and extracts the main article body.

Why this exists: scrapers return only short summaries (RSS `description`, HN
`comment_text`, Reddit `selftext`). The Claim-Evidence Matcher needs richer
context to classify support/refute correctly.

Strategy:
1. Try `trafilatura` (best-in-class boilerplate stripping for articles).
2. Fall back to a tiny regex HTML strip if trafilatura returns nothing.
3. Skip items whose URL was already enriched, or that point to image/binary.
4. Cap body to 10,000 chars to bound prompt size downstream.

Concurrency: items are fetched with a `ThreadPoolExecutor` (max 5 workers).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
import trafilatura

from ari_agent.schemas import EvidenceItem
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

MAX_BODY_CHARS = 10_000
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".mp4", ".webm", ".zip"}
SKIP_DOMAINS = {
    "twitter.com", "x.com", "youtube.com", "youtu.be",
    # Reddit: anti-bot wall returns "Please wait for verification" stub.
    # The collector already captures `selftext`, so re-fetching here adds no value.
    "reddit.com", "www.reddit.com", "old.reddit.com",
}


@dataclass(slots=True)
class EnrichStats:
    """Aggregate stats reported back by `enrich_many` for telemetry."""

    total: int = 0
    enriched: int = 0
    skipped: int = 0
    errors: int = 0
    latency_ms: int = 0


def _should_skip(url: str) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    if parsed.netloc.lower() in SKIP_DOMAINS:
        return True
    path_lower = parsed.path.lower()
    return any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS)


def _regex_html_strip(html: str) -> str:
    text = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def enrich_one(item: EvidenceItem, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[EvidenceItem, str]:
    """Return (possibly-updated item, status). Status is one of: enriched|skipped|error|cached."""
    if item.body_full:
        return item, "cached"
    if _should_skip(item.url):
        return item, "skipped"

    try:
        downloaded = trafilatura.fetch_url(item.url)
        body: str | None = None
        if downloaded:
            body = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
        if not body:
            # Fallback: plain requests + regex strip
            resp = requests.get(
                item.url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.status_code == 200 and resp.text:
                body = _regex_html_strip(resp.text)
        if body:
            body = body[:MAX_BODY_CHARS]
            return item.model_copy(update={"body_full": body}), "enriched"
        return item, "skipped"
    except Exception:  # noqa: BLE001
        return item, "error"


def enrich_many(
    items: list[EvidenceItem],
    *,
    max_workers: int = 5,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[list[EvidenceItem], EnrichStats]:
    """Concurrently enrich a list of items. Order is preserved."""
    stats = EnrichStats(total=len(items))
    if not items:
        return [], stats

    out: list[EvidenceItem] = [None] * len(items)  # type: ignore[list-item]
    with Timer() as timer, ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(enrich_one, it, timeout): i for i, it in enumerate(items)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                item, status = fut.result()
            except Exception:  # noqa: BLE001
                out[idx] = items[idx]
                stats.errors += 1
                continue
            out[idx] = item
            if status == "enriched":
                stats.enriched += 1
            elif status == "error":
                stats.errors += 1
            else:
                stats.skipped += 1
    stats.latency_ms = timer.elapsed_ms
    return out, stats
