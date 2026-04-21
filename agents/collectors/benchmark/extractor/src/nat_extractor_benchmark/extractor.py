"""Benchmark scraper: wraps AA + HF raw scrapers and normalizes to EvidenceItem/ScrapeResult.

Returns up to `input_.limit` EvidenceItems total, partitioned as:
  1. Artificial Analysis benchmarks (0 or 1 item)
  2. HuggingFace benchmarks + model card (0 or 1 item, body_full=README.md)
  3. HuggingFace discussions (fills the remaining slots, up to limit)
"""

from __future__ import annotations

from ari_core import EvidenceItem, ScrapeInput, ScrapeResult, Timer

from nat_extractor_benchmark.scrapers.artificialanalysis import (
    fetch_model_benchmarks as _fetch_aa,
)
from nat_extractor_benchmark.scrapers.huggingface import (
    fetch_benchmarks_for_model as _fetch_hf_benchmarks,
    fetch_discussions as _fetch_hf_discussions,
)

SOURCE = "benchmark"


def _summarize_benchmarks(benchmarks: list[dict], max_items: int = 10) -> str:
    """Format benchmark list as '{name}={score_str}, ...' for EvidenceItem.text."""
    if not benchmarks:
        return "(no benchmarks parsed)"
    parts = [f"{b['name']}={b['score_str']}" for b in benchmarks[:max_items]]
    if len(benchmarks) > max_items:
        parts.append(f"... (+{len(benchmarks) - max_items} more)")
    return ", ".join(parts)


def scrape(input_: ScrapeInput) -> ScrapeResult:
    """Collect LLM benchmarks and HuggingFace discussions, normalized to EvidenceItems.

    Reads from input_.extra:
        - comment_limit: max comments per HF discussion (default: 3)

    Args:
        input_: ScrapeInput. `query` is the LLM model name,
            `limit` caps the total number of EvidenceItems returned.

    Returns:
        ScrapeResult with up to `limit` EvidenceItems from AA and HF.
    """
    comment_limit = int(input_.extra.get("comment_limit", 3))
    model_query = input_.query

    with Timer() as t:
        try:
            items: list[EvidenceItem] = []

            # --- Artificial Analysis benchmarks ---
            aa_bm, aa_name, aa_provider, aa_slug = _fetch_aa(model_query)
            if aa_bm:
                aa_url = (
                    f"https://artificialanalysis.ai/models/{aa_slug}"
                    if aa_slug
                    else "https://artificialanalysis.ai/models"
                )
                items.append(
                    EvidenceItem(
                        source="artificial_analysis",
                        source_detail="artificialanalysis.ai",
                        url=aa_url,
                        title=aa_name or model_query,
                        text=f"{aa_name} benchmarks from Artificial Analysis: {_summarize_benchmarks(aa_bm)}",
                        metadata={
                            "kind": "benchmark_scores",
                            "provider": aa_provider,
                            "model_name": aa_name,
                            "slug": aa_slug,
                            "benchmarks": aa_bm,
                        },
                    )
                )

            if len(items) >= input_.limit:
                return ScrapeResult(source=SOURCE, ok=True, items=items, latency_ms=t.elapsed_ms)

            # --- HuggingFace benchmarks + model card ---
            hf_bm, hf_name, hf_provider, hf_model_id, hf_card = _fetch_hf_benchmarks(model_query)
            if hf_model_id:
                items.append(
                    EvidenceItem(
                        source="huggingface",
                        source_detail=f"huggingface.co/{hf_model_id}",
                        url=f"https://huggingface.co/{hf_model_id}",
                        title=hf_name or hf_model_id,
                        text=f"{hf_name} benchmarks from HuggingFace model card: {_summarize_benchmarks(hf_bm)}",
                        body_full=hf_card or None,
                        metadata={
                            "kind": "benchmark_scores",
                            "provider": hf_provider,
                            "model_id": hf_model_id,
                            "model_name": hf_name,
                            "benchmarks": hf_bm,
                        },
                    )
                )

                # --- HuggingFace discussions (fill remaining slots) ---
                remaining = max(0, input_.limit - len(items))
                if remaining > 0:
                    discussions = _fetch_hf_discussions(
                        hf_model_id,
                        limit=remaining,
                        comment_limit=comment_limit,
                    )
                    for d in discussions:
                        items.append(
                            EvidenceItem(
                                source="huggingface",
                                source_detail=f"huggingface.co/{hf_model_id}/discussions",
                                url=d.get("url", f"https://huggingface.co/{hf_model_id}/discussions"),
                                title=d.get("title"),
                                author=d.get("author") or None,
                                text=d.get("body", "") or "",
                                timestamp=d.get("created_at") or None,
                                score=d.get("num_comments"),
                                metadata={
                                    "kind": "discussion",
                                    "model_id": hf_model_id,
                                    "discussion_num": d.get("num"),
                                    "status": d.get("status"),
                                    "comments": d.get("comments", []),
                                },
                            )
                        )

            return ScrapeResult(
                source=SOURCE,
                ok=True,
                items=items[: input_.limit],
                latency_ms=t.elapsed_ms,
            )
        except Exception as e:  # noqa: BLE001
            return ScrapeResult(
                source=SOURCE,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=t.elapsed_ms,
            )
