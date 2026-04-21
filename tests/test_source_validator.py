"""Smoke test for the rule-based Source Validator.

Builds a hand-picked set of EvidenceItem instances spanning the trust spectrum
(arxiv > vendor blog > expert blog > skeptic > Reddit > unknown) and asserts
the score order is sensible. Writes a Markdown summary to docs/.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_ROOT = HERE.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ari_agent.schemas import EvidenceItem  # noqa: E402
from ari_agent.validators.source_validator import validate_one  # noqa: E402

REPO_ROOT = SRC_ROOT.parent
REPORT_PATH = REPO_ROOT / "docs" / "source-validator-test.md"


SAMPLES = [
    # (label, EvidenceItem)
    (
        "vendor official (Anthropic news)",
        EvidenceItem(
            source="rss",
            source_detail="anthropic_official",
            url="https://www.anthropic.com/news/claude-opus-4-7",
            author=None,
            title="Introducing Claude Opus 4.7",
            text="Opus 4.7 improves SWE-bench scores by 7.2% over Opus 4.6 (78.5% vs 71.3%). "
                 "Released April 16 2026. See https://anthropic.com/research and https://example.com",
        ),
    ),
    (
        "primary research (arXiv)",
        EvidenceItem(
            source="arxiv",
            source_detail="arxiv",
            url="https://arxiv.org/abs/2604.18584",
            author="Researcher A, Researcher B",
            title="A novel reasoning benchmark",
            text="We introduce a benchmark with 5,000 problems and report 67.4% accuracy. "
                 "Methodology in Section 3, results in Table 2. https://github.com/lab/repo",
        ),
    ),
    (
        "expert blog (Simon Willison)",
        EvidenceItem(
            source="rss",
            source_detail="simon_willison",
            url="https://simonwillison.net/2026/Apr/16/qwen-beats-opus/",
            author=None,
            title="Qwen3.6 beats Opus 4.7 at pelican drawing",
            text="I tested 3 models on the same prompt. Qwen scored 82, Opus scored 74. "
                 "https://qwen.ai and https://anthropic.com.",
        ),
    ),
    (
        "skeptic blog (Gary Marcus)",
        EvidenceItem(
            source="rss",
            source_detail="gary_marcus",
            url="https://garymarcus.substack.com/p/peak-absurdity-part-ii",
            author="Gary Marcus",
            title="Peak absurdity, Part II",
            text="You can't make this up.",  # Intentionally short -> low verifiability
        ),
    ),
    (
        "Reddit (high upvote)",
        EvidenceItem(
            source="reddit",
            source_detail="r/LocalLLaMA",
            url="https://reddit.com/r/LocalLLaMA/comments/abc/foo",
            author="bigboyparpa",
            title="Kimi K2.6 is a legit Opus 4.7 replacement",
            text="It's not really better than Opus 4.7 at anything, but it can do about 85% of the tasks.",
            score=283,
        ),
    ),
    (
        "Reddit (low upvote)",
        EvidenceItem(
            source="reddit",
            source_detail="r/LocalLLaMA",
            url="https://reddit.com/r/LocalLLaMA/comments/xyz/bar",
            author="newuser123",
            title="Random thought",
            text="just curious",
            score=0,
        ),
    ),
    (
        "GitHub (bot author)",
        EvidenceItem(
            source="github",
            source_detail="issues:anthropics/anthropic-sdk-python",
            url="https://github.com/anthropics/anthropic-sdk-python/pull/1387",
            author="stainless-app[bot]",
            title="release: 0.96.0",
            text="Automated Release PR. Full changelog: https://github.com/anthropics/anthropic-sdk-python/compare/v0.95.0...v0.96.0",
        ),
    ),
    (
        "Unknown domain",
        EvidenceItem(
            source="rss",
            source_detail="unknown_blog",
            url="https://random-personal-site.example.com/post",
            author="unknown",
            title="My take",
            text="just some opinion",
        ),
    ),
]


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Source Validator Smoke Test",
        "",
        "> 8개 샘플로 rule-based 2축 점수 합리성 검증.",
        "",
        "| # | 라벨 | Aggregate | Authority | Verifiability | URL |",
        "|---|------|-----------|-----------|---------------|-----|",
    ]
    results = []
    for i, (label, item) in enumerate(SAMPLES, 1):
        r = validate_one(item)
        results.append((label, r))
        lines.append(
            f"| {i} | {label} | **{r.aggregate:.2f}** | {r.authority.score:.2f} | "
            f"{r.verifiability.score:.2f} | {item.url[:60]}… |"
        )
    lines += ["", "## 점수 근거 (reasons)", ""]
    for label, r in results:
        lines.append(f"### {label} — {r.aggregate:.2f}")
        for reason in r.authority.reasons:
            lines.append(f"- Authority: {reason}")
        for reason in r.verifiability.reasons:
            lines.append(f"- Verifiability: {reason}")
        lines.append("")

    # Sanity: vendor > Reddit-low > unknown
    by_label = {label: r.aggregate for label, r in results}
    expected_orderings = [
        ("vendor official (Anthropic news)", ">", "Reddit (low upvote)"),
        ("vendor official (Anthropic news)", ">", "Unknown domain"),
        ("primary research (arXiv)", ">", "Unknown domain"),
        ("expert blog (Simon Willison)", ">", "Reddit (low upvote)"),
        ("Reddit (high upvote)", ">", "Reddit (low upvote)"),
    ]
    fails = []
    for left, _, right in expected_orderings:
        if by_label[left] <= by_label[right]:
            fails.append(f"{left} ({by_label[left]:.2f}) > {right} ({by_label[right]:.2f}) FAILED")
    lines += ["## Sanity Checks", ""]
    if fails:
        lines += [f"- ❌ {f}" for f in fails]
    else:
        lines.append("- ✅ All expected orderings hold.")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {REPORT_PATH}")
    print(f"Sanity: {'PASS' if not fails else 'FAIL'} ({len(fails)} violations)")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
