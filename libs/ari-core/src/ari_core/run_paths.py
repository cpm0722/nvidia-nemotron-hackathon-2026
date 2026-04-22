"""Filesystem layout helpers for a single e2e pipeline run.

All agents (e2e orchestrator, extractors, reporter) share a common
``runs/{run_id}/`` directory to exchange data via files instead of in-memory
payloads. This module is the single source of truth for that layout so the
individual agents never hard-code paths.

Layout::

    runs/{run_id}/
        query.json                            # {user_query, products}
        raw/{product_slug}/{source}.json      # extractor scrape result
        validated/{product_slug}/{source}.json  # validator filtered result
        report_{product_slug}.md              # reporter markdown (humans)
        report_{product_slug}.json            # reporter structured JSON (frontend)

``run_id`` is ``YYYYMMDD-HHMMSS-{8-char uuid}`` so that lexicographic ordering
matches chronological ordering. ``product_slug`` is ``slugify_product`` applied
to the product name so paths stay filesystem-safe across OSes.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUNS_ROOT_ENV = "ARI_RUNS_ROOT"
DEFAULT_RUNS_ROOT = Path("runs")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_product(name: str) -> str:
    """Return a filesystem-safe slug for a product name.

    Lowercases, replaces any run of non alphanumerics with a single dash, and
    strips leading/trailing dashes. An empty result falls back to ``product``
    so downstream path joins never fail.

    Args:
        name: Arbitrary product label (e.g. ``"GPT-5 Turbo"``).

    Returns:
        Slug such as ``"gpt-5-turbo"``.
    """
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "product"


def new_run_id() -> str:
    """Generate a new run identifier.

    Returns:
        ``YYYYMMDD-HHMMSS-xxxxxxxx`` where the suffix is an 8-character uuid4
        fragment. Format guarantees lexicographic = chronological ordering.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def runs_root(root: Path | str | None = None) -> Path:
    """Resolve the base ``runs/`` directory.

    Resolution order:
        1. ``root`` argument when provided (tests use this).
        2. ``ARI_RUNS_ROOT`` environment variable — set by docker-compose to
           ``/app/runs`` so every container writes into the same bind-mounted
           volume. Locally, export it to an absolute path (e.g. the repo
           root's ``runs/``) when starting agents from different cwds.
        3. ``DEFAULT_RUNS_ROOT`` (``Path("runs")``), resolved against the
           current working directory — only safe when all agents share the
           same cwd.

    Returns:
        ``Path`` (not created).
    """
    if root is not None:
        return Path(root)
    env = os.environ.get(RUNS_ROOT_ENV)
    return Path(env) if env else DEFAULT_RUNS_ROOT


def run_root(run_id: str, root: Path | str | None = None) -> Path:
    """Return ``runs/{run_id}/`` as a Path (not created)."""
    return runs_root(root) / run_id


def query_path(run_id: str, root: Path | str | None = None) -> Path:
    """Return the path to ``query.json`` for a given run."""
    return run_root(run_id, root) / "query.json"


def raw_path(
    run_id: str, product: str, source: str, root: Path | str | None = None
) -> Path:
    """Return the extractor raw output path for ``(product, source)``."""
    return run_root(run_id, root) / "raw" / slugify_product(product) / f"{source}.json"


def validated_path(
    run_id: str, product: str, source: str, root: Path | str | None = None
) -> Path:
    """Return the validator output path for ``(product, source)``."""
    return (
        run_root(run_id, root) / "validated" / slugify_product(product) / f"{source}.json"
    )


def report_path(run_id: str, product: str, root: Path | str | None = None) -> Path:
    """Return the reporter markdown output path (``report_{product}.md``)."""
    return run_root(run_id, root) / f"report_{slugify_product(product)}.md"


def report_json_path(run_id: str, product: str, root: Path | str | None = None) -> Path:
    """Return the reporter structured JSON output path (``report_{product}.json``).

    Sibling to ``report_path`` — the reporter writes both files per product.
    Frontend consumes the JSON; humans read the markdown.
    """
    return run_root(run_id, root) / f"report_{slugify_product(product)}.json"


def ensure_parent(path: Path) -> Path:
    """Create the parent directory of ``path`` if needed; return ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> Path:
    """Atomically write ``data`` as UTF-8 JSON to ``path``.

    Creates parent directories as needed. Uses ``default=str`` so unexpected
    datetime/UUID values serialize instead of raising. Returns the resolved
    path for convenience.

    Note:
        "Atomic" here means write-to-temp + replace within the same directory,
        which is the best we can do portably across macOS/Linux.
    """
    ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def read_json(path: Path) -> Any:
    """Read and parse JSON from ``path`` (UTF-8)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> Path:
    """Atomically write ``text`` (UTF-8) to ``path``, creating parents as needed."""
    ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path
