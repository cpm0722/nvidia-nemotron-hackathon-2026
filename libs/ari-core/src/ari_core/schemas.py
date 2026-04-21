"""Shared Pydantic schemas for extractor agent outputs.

All source-specific scrapers normalize their results to EvidenceItem so that
downstream validators and aggregators can operate on a single shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScrapeInput(BaseModel):
    """Unified input across scrapers. Fields beyond `query` are optional hints."""

    query: str = Field(..., description="Primary search phrase, e.g. 'Claude Opus 4.7'")
    limit: int = Field(20, ge=1, le=100, description="Max items to return")
    since_days: int = Field(30, ge=1, le=365, description="Recency window in days")
    extra: dict[str, Any] = Field(default_factory=dict, description="Source-specific hints")


class EvidenceItem(BaseModel):
    """A single evidence record. All scrapers normalize to this shape."""

    source: str = Field(..., description="Short source tag, e.g. 'reddit' / 'arxiv' / 'geeknews'")
    source_detail: str = Field(..., description="More specific origin, e.g. 'r/LocalLLaMA'")
    url: str
    author: str | None = None
    title: str | None = None
    text: str
    body_full: str | None = Field(
        None,
        description="Full extracted body if the item was further enriched downstream.",
    )
    timestamp: str | None = Field(None, description="ISO 8601 string if known")
    score: int | None = Field(None, description="Upvotes/reactions if any")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScrapeResult(BaseModel):
    """Wrapper returned from each scraper for easier aggregation."""

    source: str
    ok: bool
    items: list[EvidenceItem] = Field(default_factory=list)
    error: str | None = None
    latency_ms: int | None = None
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
