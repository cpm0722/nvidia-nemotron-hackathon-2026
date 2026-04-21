"""arca.live scraper: wraps the HTML crawler and normalizes to EvidenceItem/ScrapeResult."""

from ari_core import EvidenceItem, ScrapeInput, ScrapeResult, Timer, iso
from nat_extractor_arcalive.crawler import crawl

SOURCE = "arcalive"


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Search arca.live for `query` and return top-N posts as EvidenceItems.

    Reads board and max_pages from input_.extra. Results are sorted by
    comment count → likes → recency, and the top-N posts are returned.

    Args:
        input_: ScrapeInput with query, limit, and optional extra keys:
            - board: arca.live channel slug (default: "alpaca")
            - max_pages: search result pages to scan (default: 2)

    Returns:
        ScrapeResult with normalized EvidenceItem records.
    """
    board = str(input_.extra.get("board", "alpaca"))
    max_pages = int(input_.extra.get("max_pages", 2))

    with Timer() as t:
        try:
            crawl_result = crawl(input_.query, board, max_pages, limit=input_.limit)

            items: list[EvidenceItem] = [
                EvidenceItem(
                    source=SOURCE,
                    source_detail=f"arca.live/b/{board}",
                    url=post.url,
                    title=post.title,
                    text=post.body,
                    timestamp=iso(post.time),
                    score=post.like,
                    metadata={
                        "rank": post.rank,
                        "dislike": post.dislike,
                        "num_comments": post.num_comments,
                        "comments": [c.model_dump() for c in post.comments],
                    },
                )
                for post in crawl_result.result
            ]

            return ScrapeResult(
                source=SOURCE,
                ok=True,
                items=items,
                latency_ms=t.elapsed_ms,
            )
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source=SOURCE,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
