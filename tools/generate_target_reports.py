"""타깃 모델별 커뮤니티 신호 리포트 생성기.

각 데모 타깃(Claude Opus 4.7, Nemotron-3 Super)에 대해 등록된 스크래퍼를
호출하고, 결과를 한국어 마크다운 리포트로 정리한다.

이 스크립트는 아직 LLM(Claim Extractor / Synthesizer)을 거치지 않은
원본 증거(raw evidence)만 다룬다. 다음 단계인 NAT 에이전트 워크플로가
이 리포트를 입력 삼아 주장 vs 증거 매칭을 수행할 예정이다.

Usage:
    cd src && PYTHONPATH=. python3 tools/generate_target_reports.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC_ROOT = HERE.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ari_agent.nat_tools import run_tool  # noqa: E402
from ari_agent.schemas import ScrapeResult  # noqa: E402

REPO_ROOT = SRC_ROOT.parent
DOCS_DIR = REPO_ROOT / "docs"

# ----------------------------------------------------------------------------
# 타깃 설정
# ----------------------------------------------------------------------------

TARGETS: dict[str, dict[str, Any]] = {
    "claude-opus-4.7": {
        "display_name": "Claude Opus 4.7",
        "primary_query": "Claude Opus 4.7",
        "secondary_query": "Claude Opus",  # 결과 부족 시 fallback
        "github_queries": [
            "claude opus repo:anthropics/anthropic-sdk-python",
            "claude opus 4 repo:anthropics/courses",
            '"opus 4" in:title,body language:python',
        ],
        "reddit_subs": ["LocalLLaMA", "ClaudeAI", "singularity"],
        "hn_query": "Claude Opus 4.7",
        "rss_feeds": [
            ("simon_willison", "claude"),
            ("latent_space", "claude"),
            ("gary_marcus", "claude"),
            ("ai_snake_oil", "claude"),
            ("import_ai", "claude"),
            ("techcrunch_ai", "claude"),
            ("alignment_forum", "claude"),
        ],
        "korean_feeds": [
            ("geeknews", "Claude"),
            ("kakao_enterprise", "claude"),
        ],
        "skeptic_feeds": [
            ("gary_marcus", "claude"),
            ("ai_snake_oil", "claude"),
            ("ben_recht", "claude"),
        ],
        "include_hf_papers": False,  # Claude는 모델카드/논문 공개 X
    },
    "nemotron-3-super": {
        "display_name": "NVIDIA Nemotron-3 Super (120B-A12B)",
        "primary_query": "nemotron-3-super",
        "secondary_query": "Nemotron",
        "github_queries": [
            "nemotron repo:NVIDIA/NeMo-Agent-Toolkit",
            "nemotron repo:NVIDIA/TensorRT-LLM",
            "nemotron repo:NVIDIA/Megatron-LM",
            '"nemotron-3" in:title,body',
        ],
        "reddit_subs": ["LocalLLaMA", "MachineLearning", "singularity"],
        "hn_query": "Nemotron",
        "rss_feeds": [
            ("simon_willison", "nemotron"),
            ("latent_space", "nemotron"),
            ("sebastian_raschka", "nemotron"),
            ("import_ai", "nemotron"),
            ("techcrunch_ai", "nvidia nemotron"),
            ("ben_recht", "nemotron"),
        ],
        "korean_feeds": [
            ("geeknews", "Nemotron"),
            ("kakao_enterprise", "nemotron"),
        ],
        "skeptic_feeds": [
            ("gary_marcus", "nemotron"),
            ("ai_snake_oil", "nemotron"),
            ("ben_recht", "nemotron"),
        ],
        "include_hf_papers": True,
    },
}


# ----------------------------------------------------------------------------
# 헬퍼
# ----------------------------------------------------------------------------


def _call(tool: str, query: str, **extra) -> ScrapeResult:
    try:
        return ScrapeResult.model_validate(
            run_tool(tool, query=query, limit=10, since_days=120, extra=extra)
        )
    except Exception as e:  # noqa: BLE001
        return ScrapeResult(source=tool, ok=False, error=f"{type(e).__name__}: {e}", latency_ms=0)


def _fmt_item(item) -> str:
    """리포트의 단일 항목 한 줄 마크다운."""
    title = item.title or "(제목 없음)"
    title = title.strip().replace("\n", " ")[:120]
    author = item.author or "익명/미상"
    ts = (item.timestamp or "").split("T")[0] if item.timestamp else "—"
    score = f" · 👍 {item.score}" if item.score is not None else ""
    snippet = (item.text or "").strip().replace("\n", " ")[:280]
    return (
        f"- **[{title}]({item.url})**  \n"
        f"  `{item.source_detail}` · {author} · {ts}{score}  \n"
        f"  > {snippet}{'…' if len(item.text or '') > 280 else ''}"
    )


def _section_header(name: str, results: list[ScrapeResult]) -> str:
    n_total = sum(len(r.items) for r in results)
    n_ok = sum(1 for r in results if r.ok)
    return f"### {name} — {n_ok}/{len(results)} 호출 성공, 총 {n_total}건\n"


def _word_freq(results: list[ScrapeResult], top_n: int = 15) -> list[tuple[str, int]]:
    """간단한 빈도 분석 (영문 위주, 한글은 그대로 유지)."""
    bag: list[str] = []
    stop = {
        "the", "and", "for", "with", "from", "this", "that", "have", "are",
        "was", "but", "not", "you", "your", "all", "can", "will", "has",
        "its", "use", "using", "use", "into", "they", "them", "more",
        "we", "i", "is", "of", "to", "in", "on", "a", "an", "be", "as",
        "by", "or", "it", "if", "so", "do", "did", "no", "yes", "than",
        "when", "what", "how", "which", "should", "would", "could", "may",
        "https", "http",
    }
    for r in results:
        for it in r.items:
            text = f"{it.title or ''} {it.text or ''}".lower()
            for tok in text.split():
                tok = tok.strip(".,!?:;'\"()[]{}<>“”‘’—…/\\|").strip()
                if not tok or len(tok) < 3 or tok in stop or tok.isdigit():
                    continue
                bag.append(tok)
    return Counter(bag).most_common(top_n)


# ----------------------------------------------------------------------------
# 리포트 생성
# ----------------------------------------------------------------------------


def gather(target_id: str, cfg: dict[str, Any]) -> dict[str, list[ScrapeResult]]:
    """타깃 1건에 대해 카테고리별로 스크래퍼 호출 → 결과 dict 반환."""
    print(f"\n=== {cfg['display_name']} 수집 시작 ===")
    out: dict[str, list[ScrapeResult]] = {
        "github": [],
        "reddit": [],
        "hackernews": [],
        "rss_general": [],
        "rss_korean": [],
        "rss_skeptic": [],
        "huggingface": [],
    }

    # GitHub (각 repo 쿼리)
    for q in cfg["github_queries"]:
        print(f"  github: {q}")
        out["github"].append(_call("scrape_github_issues", q))

    # Reddit
    print(f"  reddit: {cfg['primary_query']} in {cfg['reddit_subs']}")
    out["reddit"].append(_call("scrape_reddit", cfg["primary_query"], subreddits=cfg["reddit_subs"]))

    # HackerNews
    print(f"  hn: {cfg['hn_query']}")
    out["hackernews"].append(_call("scrape_hackernews", cfg["hn_query"]))

    # RSS — general / korean / skeptic 분리
    for key, q in cfg["rss_feeds"]:
        print(f"  rss[gen]: {key} q={q!r}")
        out["rss_general"].append(_call("scrape_rss_feed", q, feed_key=key))
    for key, q in cfg["korean_feeds"]:
        print(f"  rss[ko]:  {key} q={q!r}")
        out["rss_korean"].append(_call("scrape_rss_feed", q, feed_key=key))
    for key, q in cfg["skeptic_feeds"]:
        print(f"  rss[skp]: {key} q={q!r}")
        out["rss_skeptic"].append(_call("scrape_rss_feed", q, feed_key=key))

    # HuggingFace Papers
    if cfg.get("include_hf_papers"):
        print(f"  hf: {cfg['secondary_query']}")
        out["huggingface"].append(_call("scrape_hf_papers", cfg["secondary_query"]))

    return out


def render(target_id: str, cfg: dict[str, Any], data: dict[str, list[ScrapeResult]]) -> str:
    ts = datetime.now(tz=timezone.utc).isoformat()
    n_total = sum(len(r.items) for cat in data.values() for r in cat)
    n_calls = sum(len(cat) for cat in data.values())

    lines: list[str] = []
    lines += [
        f"# {cfg['display_name']} — 커뮤니티 신호 리포트",
        "",
        f"> **수집 시각:** {ts}  ",
        f"> **타깃 ID:** `{target_id}`  ",
        f"> **호출 수:** {n_calls}건  ",
        f"> **수집된 증거 항목:** {n_total}건  ",
        "> **단계:** raw evidence 수집 (LLM Claim Extractor / Synthesizer 통과 전)",
        "",
        "---",
        "",
        "## 0. 한 줄 요약",
        "",
        f"`{cfg['display_name']}`에 대한 멀티소스 증거를 수집한 결과, "
        f"**총 {n_total}건**의 항목이 확보되었다. "
        "이 리포트는 raw evidence 단계로, 다음 NAT 워크플로 단계에서 "
        "(1) 공식 모델카드/블로그에서 추출한 주장과 (2) 본 증거 풀을 매칭하여 "
        "지지/반박/중립으로 분류하는 작업이 이어진다.",
        "",
    ]

    # 1. GitHub
    lines += ["## 1. GitHub Issues / Pull Requests", "", _section_header("GitHub", data["github"])]
    for r in data["github"]:
        if not r.ok:
            lines.append(f"- ❌ 호출 실패: `{r.error}`")
            continue
        if not r.items:
            lines.append("- (해당 쿼리에서 결과 없음)")
            continue
        for it in r.items[:5]:
            lines.append(_fmt_item(it))
        if len(r.items) > 5:
            lines.append(f"- _… 외 {len(r.items) - 5}건 생략_")
    lines.append("")

    # 2. Reddit
    lines += ["## 2. Reddit (`.json` 무인증 fallback)", "", _section_header("Reddit", data["reddit"])]
    for r in data["reddit"]:
        if not r.ok:
            lines.append(f"- ❌ 호출 실패: `{r.error}`")
            continue
        if not r.items:
            lines.append("- (결과 없음)")
            continue
        for it in r.items[:8]:
            lines.append(_fmt_item(it))
    lines.append("")

    # 3. HackerNews
    lines += ["## 3. HackerNews (Algolia search)", "", _section_header("HN", data["hackernews"])]
    for r in data["hackernews"]:
        if not r.ok:
            lines.append(f"- ❌ 호출 실패: `{r.error}`")
            continue
        if not r.items:
            lines.append("- (결과 없음)")
            continue
        for it in r.items[:8]:
            lines.append(_fmt_item(it))
    lines.append("")

    # 4. RSS (영어권 전문가/매체)
    lines += [
        "## 4. RSS — 영어권 전문가/매체",
        "",
        _section_header("RSS general", data["rss_general"]),
    ]
    any_general = False
    for r in data["rss_general"]:
        if not r.ok:
            lines.append(f"- ❌ `{r.source}` 실패: {r.error}")
            continue
        if not r.items:
            continue
        any_general = True
        feed = r.items[0].source_detail if r.items else "(unknown)"
        lines.append(f"\n#### `{feed}` — {len(r.items)}건")
        for it in r.items[:3]:
            lines.append(_fmt_item(it))
    if not any_general:
        lines.append("- (어느 영어권 RSS에서도 쿼리 매칭 결과 없음)")
    lines.append("")

    # 5. 회의론 (skeptic) 레이어 — 별도 강조
    lines += [
        "## 5. 회의론 / 비판 레이어 (Skeptic Sources)",
        "",
        "> 균형 잡힌 evidence map을 위해 별도 섹션으로 분리. ⑦ Skeptic 레이어 (Gary Marcus, AI Snake Oil, Ben Recht 등)",
        "",
        _section_header("Skeptic", data["rss_skeptic"]),
    ]
    any_skeptic = False
    for r in data["rss_skeptic"]:
        if not r.ok:
            lines.append(f"- ❌ `{r.source}` 실패: {r.error}")
            continue
        if not r.items:
            continue
        any_skeptic = True
        feed = r.items[0].source_detail if r.items else "(unknown)"
        lines.append(f"\n#### `{feed}` — {len(r.items)}건")
        for it in r.items[:3]:
            lines.append(_fmt_item(it))
    if not any_skeptic:
        lines.append(
            "- (현재 회의론 RSS에서 본 모델 직접 언급 없음. "
            "Synthesizer는 'low skeptic signal'로 표시 권장)"
        )
    lines.append("")

    # 6. 한국어 반응
    lines += [
        "## 6. 한국어 커뮤니티 반응",
        "",
        "> 우선순위는 낮으나 멀티링구얼 신호 수집 능력 시현 + Peer-review 점수 가점용으로 필수 포함.",
        "",
        _section_header("Korean", data["rss_korean"]),
    ]
    any_korean = False
    for r in data["rss_korean"]:
        if not r.ok:
            lines.append(f"- ❌ `{r.source}` 실패: {r.error}")
            continue
        if not r.items:
            continue
        any_korean = True
        feed = r.items[0].source_detail if r.items else "(unknown)"
        lines.append(f"\n#### `{feed}` — {len(r.items)}건")
        for it in r.items[:5]:
            lines.append(_fmt_item(it))
    if not any_korean:
        lines.append(
            "- (한국어 소스에서 본 모델 직접 언급 없음. "
            "Synthesizer 리포트에는 '국내 커뮤니티 단계 신호 미감지 — 추후 재수집 권장'으로 명시)"
        )
    lines.append("")

    # 7. HuggingFace Papers
    if cfg.get("include_hf_papers"):
        lines += [
            "## 7. HuggingFace Papers",
            "",
            _section_header("HF Papers", data["huggingface"]),
        ]
        for r in data["huggingface"]:
            if not r.ok:
                lines.append(f"- ❌ 호출 실패: {r.error}")
                continue
            if not r.items:
                lines.append(
                    "- (HF Papers 일일 큐레이션에 본 모델 관련 항목 없음 — "
                    "특정 arxiv id 직접 조회 경로 추가 검토 필요)"
                )
                continue
            for it in r.items[:5]:
                lines.append(_fmt_item(it))
        lines.append("")

    # 8. 키워드 빈도
    all_results = (
        data["github"] + data["reddit"] + data["hackernews"]
        + data["rss_general"] + data["rss_korean"] + data["rss_skeptic"]
        + data["huggingface"]
    )
    freq = _word_freq(all_results, top_n=20)
    lines += [
        "## 8. 키워드 빈도 (raw, 상위 20)",
        "",
        "> stop-word 필터링한 단순 빈도. Claim Extractor 단계에서 의미 단위로 재정제 예정.",
        "",
    ]
    if not freq:
        lines.append("- (충분한 텍스트 없음)")
    else:
        lines.append("| 키워드 | 빈도 |")
        lines.append("|---|---|")
        for word, count in freq:
            lines.append(f"| {word} | {count} |")
    lines.append("")

    # 9. Synthesizer 단계로 넘길 것
    lines += [
        "## 9. 다음 단계 입력 후보 (Synthesizer 위에서 처리)",
        "",
        "현재 리포트는 raw evidence 단계이므로 아직 의미적 매칭/판정이 없다. NAT 워크플로의 다음 단계는:",
        "",
        "1. **Claim Extractor** — 공식 모델카드/블로그 URL을 입력 받아 검증 가능한 주장 N개 추출",
        "2. **Claim-Evidence Matcher** — 본 리포트의 각 증거 항목을 주장에 매칭 + 지지/반박/중립 분류",
        "3. **Source Validator (경량)** — 각 항목 source_detail에 대해 Authority/Verifiability 점수 부여",
        "4. **Synthesizer** — 주장별 Signal Balance + 인용 포함 최종 리포트 생성",
        "",
        "본 리포트는 Step 2의 입력 풀로 그대로 NAT function에 전달 가능 (`EvidenceItem` 스키마 일치).",
        "",
        "---",
        "",
        "## 부록: 호출 상세 (디버그용)",
        "",
        "| 카테고리 | 호출 수 | 성공 | 항목 합계 | 평균 latency (ms) |",
        "|---|---|---|---|---|",
    ]
    for cat, results in data.items():
        n_calls_ = len(results)
        n_ok = sum(1 for r in results if r.ok)
        n_items = sum(len(r.items) for r in results)
        latencies = [r.latency_ms for r in results if r.latency_ms is not None]
        avg_lat = int(sum(latencies) / len(latencies)) if latencies else "—"
        lines.append(f"| {cat} | {n_calls_} | {n_ok} | {n_items} | {avg_lat} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for target_id, cfg in TARGETS.items():
        data = gather(target_id, cfg)
        report = render(target_id, cfg, data)
        path = DOCS_DIR / f"report-{target_id}.md"
        path.write_text(report, encoding="utf-8")
        print(f"\n✅ 저장: {path}  ({len(report.splitlines())}줄)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
