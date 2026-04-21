"""GitHub Issues + Discussions scraper via REST API.

Auth: optional PAT via `GITHUB_TOKEN` env var (5000 req/hr).
Unauthenticated falls back to 60 req/hr and is only suitable for smoke tests.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from ari_agent.schemas import EvidenceItem, ScrapeInput, ScrapeResult
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT, Timer

API_ROOT = "https://api.github.com"


def _headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _search_issues(query: str, limit: int) -> list[dict[str, Any]]:
    # GitHub issue search: https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests
    params = {"q": query, "per_page": min(limit, 100), "sort": "updated", "order": "desc"}
    resp = requests.get(
        f"{API_ROOT}/search/issues",
        params=params,
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Search GitHub issues/PRs matching the query."""
    with Timer() as t:
        try:
            raw = _search_issues(input_.query, input_.limit)
            items = [
                EvidenceItem(
                    source="github",
                    source_detail=f"issues:{item['repository_url'].split('/repos/')[-1]}",
                    url=item["html_url"],
                    author=(item.get("user") or {}).get("login"),
                    title=item.get("title"),
                    text=(item.get("body") or "")[:2000],
                    timestamp=item.get("updated_at"),
                    score=item.get("reactions", {}).get("total_count"),
                    metadata={
                        "state": item.get("state"),
                        "labels": [l.get("name") for l in item.get("labels", [])],
                        "comments": item.get("comments"),
                    },
                )
                for item in raw
            ]
            return ScrapeResult(source="github", ok=True, items=items, latency_ms=t.elapsed_ms)
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source="github",
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
