"""HuggingFace Papers API scraper.

HF Papers is a daily-curated list of papers with community upvotes,
comments, and linked reproduction Spaces — high-signal for the
"independent reproduction" evidence layer.

Endpoint: https://huggingface.co/api/papers?limit=N (no auth).
"""

from __future__ import annotations

import requests

from ari_agent.schemas import EvidenceItem, ScrapeInput, ScrapeResult
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

PAPERS_API = "https://huggingface.co/api/papers"


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Fetch daily HF papers and filter titles/summaries by query substring."""
    with Timer() as t:
        try:
            resp = requests.get(
                PAPERS_API,
                params={"limit": min(input_.limit * 3, 50)},
                headers={"User-Agent": USER_AGENT},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            raw = resp.json()
            q = input_.query.lower().strip()
            items: list[EvidenceItem] = []
            for rec in raw:
                paper = rec.get("paper") or rec
                title = paper.get("title", "")
                summary = paper.get("summary", "") or ""
                text = f"{title}\n{summary}"
                if q and q not in text.lower():
                    continue
                arxiv_id = paper.get("id") or paper.get("arxivId")
                url = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else "https://huggingface.co/papers"
                items.append(
                    EvidenceItem(
                        source="huggingface",
                        source_detail="papers",
                        url=url,
                        author=", ".join(
                            (a.get("name") or a.get("user") or "")
                            for a in paper.get("authors", [])[:5]
                        ) or None,
                        title=title,
                        text=summary[:2000],
                        timestamp=paper.get("publishedAt") or rec.get("publishedAt"),
                        score=rec.get("numComments"),
                        metadata={
                            "upvotes": paper.get("upvotes"),
                            "arxiv_id": arxiv_id,
                            "num_comments": rec.get("numComments"),
                        },
                    )
                )
                if len(items) >= input_.limit:
                    break
            return ScrapeResult(source="huggingface", ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="huggingface",
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
