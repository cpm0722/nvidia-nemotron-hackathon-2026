"""Smoke tests for each scraper.

This is not a unit-test suite — it makes real network calls and records
latency + result counts to a Markdown report. Intended to run once at
Day 1 to verify all sources respond before the agent loop is wired up.

Usage:
    cd src
    PYTHONPATH=. python3 tests/test_scrapers.py

Outputs:
    /Users/user/Documents/nvidia-hackathon/docs/scraper-test-report.md
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Ensure src/ is on sys.path for ari_agent import
HERE = Path(__file__).resolve().parent
SRC_ROOT = HERE.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ari_agent.nat_tools import run_tool  # noqa: E402
from ari_agent.schemas import ScrapeInput, ScrapeResult  # noqa: E402

REPO_ROOT = SRC_ROOT.parent
REPORT_PATH = REPO_ROOT / "docs" / "scraper-test-report.md"

QUERY_PRIMARY = "Claude Opus 4.7"
QUERY_SECONDARY = "Nemotron"


def run_case(name: str, tool: str, query: str, **kwargs) -> dict:
    """Run one tool invocation, capture outcome."""
    print(f"[ run ] {name} ({tool}) q={query!r} extra={kwargs}", flush=True)
    try:
        result_dict = run_tool(tool, query=query, limit=5, since_days=30, extra=kwargs)
        result = ScrapeResult.model_validate(result_dict)
        ok = result.ok
        n = len(result.items)
        err = result.error
        sample = result.items[0].model_dump() if result.items else None
        print(f"[ {'OK ' if ok else 'ERR'} ] {name}: items={n} ms={result.latency_ms} err={err}", flush=True)
    except Exception as e:  # noqa: BLE001
        ok, n, err, sample = False, 0, f"{type(e).__name__}: {e}", None
        result = None
        print(f"[FAIL] {name}: {err}\n{traceback.format_exc()}", flush=True)
    return {
        "case": name,
        "tool": tool,
        "query": query,
        "extra": kwargs,
        "ok": ok,
        "n_items": n,
        "error": err,
        "latency_ms": result.latency_ms if result else None,
        "sample": sample,
    }


def main() -> int:
    cases = [
        # GitHub issues — query must include repo hint to avoid "SEARCH is too broad" errors
        ("GitHub: Nemotron in NVIDIA repos", "scrape_github_issues", "nemotron repo:NVIDIA/NeMo-Agent-Toolkit"),
        ("GitHub: Claude Opus sdk issues", "scrape_github_issues", "claude repo:anthropics/anthropic-sdk-python"),
        # Reddit .json fallback
        ("Reddit: Claude Opus 4.7", "scrape_reddit", QUERY_PRIMARY, {"subreddits": ["LocalLLaMA", "ClaudeAI"]}),
        ("Reddit: Nemotron", "scrape_reddit", QUERY_SECONDARY, {"subreddits": ["LocalLLaMA", "MachineLearning"]}),
        # HackerNews Algolia
        ("HN Algolia: Claude Opus 4.7", "scrape_hackernews", QUERY_PRIMARY),
        ("HN Algolia: Nemotron", "scrape_hackernews", QUERY_SECONDARY),
        # RSS — official blogs
        ("RSS OpenAI", "scrape_rss_feed", "gpt", {"feed_key": "openai"}),
        ("RSS DeepMind", "scrape_rss_feed", "", {"feed_key": "deepmind"}),
        ("RSS Simon Willison (Claude)", "scrape_rss_feed", "claude", {"feed_key": "simon_willison"}),
        ("RSS Latent Space", "scrape_rss_feed", "", {"feed_key": "latent_space"}),
        ("RSS Gary Marcus (skeptic)", "scrape_rss_feed", "", {"feed_key": "gary_marcus"}),
        # Korean required
        ("RSS GeekNews (AI)", "scrape_rss_feed", "AI", {"feed_key": "geeknews"}),
        ("RSS Kakao Enterprise", "scrape_rss_feed", "", {"feed_key": "kakao_enterprise"}),
        # HuggingFace papers
        ("HF Papers latest", "scrape_hf_papers", ""),
        ("HF Papers: Nemotron", "scrape_hf_papers", "nemotron"),
        # arXiv (new)
        ("arXiv: Nemotron", "scrape_arxiv", "nemotron"),
        ("arXiv: Claude Opus", "scrape_arxiv", "claude opus"),
    ]

    rows = []
    for case in cases:
        if len(case) == 3:
            name, tool, q = case
            extra = {}
        else:
            name, tool, q, extra = case
        rows.append(run_case(name, tool, q, **extra))

    report_md = render_report(rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report_md, encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}", flush=True)

    # Emit JSON side-car for machine parsing
    json_path = REPORT_PATH.with_suffix(".json")
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Raw JSON: {json_path}", flush=True)

    return 0 if all(r["ok"] for r in rows) else 1


def render_report(rows: list[dict]) -> str:
    ts = datetime.utcnow().isoformat() + "Z"
    ok_count = sum(1 for r in rows if r["ok"])
    total = len(rows)
    lines = [
        "# Scraper Smoke Test Report",
        "",
        f"> 실행 시각: {ts}",
        f"> 결과: **{ok_count}/{total} pass**",
        f"> 환경: Python {sys.version.split()[0]}, GITHUB_TOKEN={'set' if os.getenv('GITHUB_TOKEN') else 'unset'}",
        "",
        "## Summary",
        "",
        "| # | Case | Tool | Query | Status | n | Latency (ms) | Error |",
        "|---|------|------|-------|--------|---|--------------|-------|",
    ]
    for i, r in enumerate(rows, 1):
        status = "✅" if r["ok"] else "❌"
        err = (r["error"] or "").replace("|", "\\|")[:80]
        lines.append(
            f"| {i} | {r['case']} | `{r['tool']}` | `{r['query']}` | {status} | {r['n_items']} | {r['latency_ms']} | {err} |"
        )
    lines += ["", "## Samples", ""]
    for i, r in enumerate(rows, 1):
        if r.get("sample"):
            s = r["sample"]
            lines += [
                f"### {i}. {r['case']}",
                "",
                f"- source: `{s.get('source')}` / detail: `{s.get('source_detail')}`",
                f"- title: {s.get('title')}",
                f"- author: {s.get('author')} | score: {s.get('score')} | ts: {s.get('timestamp')}",
                f"- url: {s.get('url')}",
                f"- text (truncated):",
                "",
                "  > " + (s.get("text", "")[:300].replace("\n", " ")),
                "",
            ]
    lines += [
        "",
        "## Interpretation",
        "",
        "- GitHub 검색은 repo 힌트(`repo:OWNER/NAME`)가 있어야 효율적. 글로벌 검색은 rate 및 relevance 측면에서 비권장.",
        "- Reddit `.json` fallback은 User-Agent 고유화 필수. 429 발생 시 exponential backoff 필요.",
        "- RSS는 feed별 item timestamp 포맷이 제각각 → 정규화 필요 (downstream Matcher 단계에서 처리).",
        "- HF Papers는 query 없이도 일일 curated list가 유용한 seed source.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
