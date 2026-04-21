"""Shared helpers for scraper modules."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

USER_AGENT = "ari-agent/0.1 (hackathon; contact: ari-agent@example.com)"

DEFAULT_TIMEOUT_SECONDS = 15


def iso(dt: datetime) -> str:
    """Render datetime as ISO 8601 with trailing Z when UTC."""
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def since_timestamp(days: int) -> datetime:
    """Return UTC cutoff datetime N days ago."""
    return datetime.now(tz=timezone.utc) - timedelta(days=days)


class Timer:
    """Context manager that exposes `elapsed_ms` as a live property.

    Readable both inside and after the `with` block.
    """

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        self._end: float | None = None
        return self

    def __exit__(self, *exc):  # noqa: ANN001
        self._end = time.perf_counter()

    @property
    def elapsed_ms(self) -> int:
        end = self._end if self._end is not None else time.perf_counter()
        return int((end - self._start) * 1000)
