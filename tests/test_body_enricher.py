"""Smoke test for the body enricher.

Picks a few real URLs (mix of Substack RSS, GitHub issue, HN comment thread)
and confirms trafilatura extracts something non-trivial. Writes a small
report to docs/body-enricher-test.md so the team can eyeball results.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_ROOT = HERE.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ari_agent.enrichers.body_fetcher import enrich_many  # noqa: E402
from ari_agent.schemas import EvidenceItem  # noqa: E402

REPO_ROOT = SRC_ROOT.parent
REPORT_PATH = REPO_ROOT / "docs" / "body-enricher-test.md"


SAMPLE_URLS = [
    ("Substack article", "https://simonwillison.net/2026/Apr/16/qwen-beats-opus/"),
    ("HN story link", "https://www.anthropic.com/news/claude-opus-4-7"),
    ("Reddit post", "https://reddit.com/r/LocalLLaMA/comments/1srd2cc/opus_47_max_subscriber_switching_to_kimi_26/"),
    ("GitHub issue", "https://github.com/anthropics/anthropic-sdk-python/issues/1383"),
    ("Twitter (should skip)", "https://twitter.com/anthropicai/status/1234"),
]


def main() -> int:
    items = [
        EvidenceItem(
            source="test",
            source_detail=label,
            url=url,
            text="(stub — to be replaced by full body)",
        )
        for label, url in SAMPLE_URLS
    ]
    enriched, stats = enrich_many(items, max_workers=4)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Body Enricher Smoke Test",
        "",
        f"> 실행: stats — total={stats.total}, enriched={stats.enriched}, "
        f"skipped={stats.skipped}, errors={stats.errors}, latency={stats.latency_ms}ms",
        "",
        "## URL별 결과",
        "",
        "| # | 라벨 | URL | 상태 | 본문 길이 (chars) | 첫 200자 |",
        "|---|------|-----|------|------------------|---------|",
    ]
    for i, (orig, enr) in enumerate(zip(items, enriched), 1):
        body = enr.body_full or ""
        status = "✅ enriched" if body else "⚠️ no-body"
        snippet = body[:200].replace("\n", " ").replace("|", "\\|") if body else "—"
        lines.append(
            f"| {i} | {orig.source_detail} | {orig.url[:60]}… | {status} | {len(body)} | {snippet} |"
        )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {REPORT_PATH}")
    print(f"Stats: enriched={stats.enriched}/{stats.total}, errors={stats.errors}")
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
