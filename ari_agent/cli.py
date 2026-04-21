"""ari_agent CLI — single entry point for OpenClaw JS skills.

OpenClaw skills spawn `python -m ari_agent.cli <subcommand> [--flags]`. Each
subcommand writes a single JSON object to stdout and exits with code 0 on
success. Errors go to stderr with non-zero exit.

Subcommands (10):
  scrape_rss, scrape_arxiv, scrape_reddit, scrape_hackernews,
  scrape_github, scrape_hf_papers     — pure-HTTP scrapers, args via flags
  enrich_bodies, validate_sources     — consume evidence JSON from stdin
  extract_claims                      — LLM-backed, args via --url
  synthesize_report                   — LLM-backed, {claims, evidence} from stdin

Also:
  health                              — print llm_client.describe()

Exit codes:
  0  success
  2  input validation error (bad flags / stdin JSON)
  3  runtime error (HTTP / LLM / parsing)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

import requests

from ari_agent import llm_client
from ari_agent.enrichers.body_fetcher import enrich_many
from ari_agent.schemas import EvidenceItem, ScrapeInput
from ari_agent.scrapers import arxiv as s_arxiv
from ari_agent.scrapers import github as s_github
from ari_agent.scrapers import hackernews as s_hn
from ari_agent.scrapers import huggingface as s_hf
from ari_agent.scrapers import reddit as s_reddit
from ari_agent.scrapers import rss as s_rss
from ari_agent.scrapers.base import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from ari_agent.validators.source_validator import validate_many


CLAIM_EXTRACTOR_PROMPT = """You are an analyst preparing an evidence map for a new AI model release.

Below is the raw content of an official source (model card / release blog / paper abstract):
---
{content}
---

Extract every VERIFIABLE quantitative or capability claim. A claim is verifiable if a
community member could in principle confirm or refute it from outside data.

Return strictly valid JSON of the form:
{{
  "model_name": "...",
  "claims": [
    {{
      "id": "C1",
      "text": "<one sentence claim>",
      "kind": "benchmark|capability|scale|cost|safety",
      "evidence_hints": ["<keyword>", "<keyword>"]
    }}
  ]
}}

Rules:
- Up to 8 claims, most concrete first.
- `evidence_hints` are 2-4 short search keywords useful for downstream collectors.
- Output JSON only, no prose, no markdown fences.
"""

SYNTHESIZER_SYSTEM = (
    "당신은 중립적인 리서치 애널리스트입니다. 사고 과정을 출력하지 말고 "
    "최종 마크다운 리포트만 바로 출력하세요."
)

SYNTHESIZER_PROMPT = """당신은 AI 모델 릴리즈를 평가하는 리서치 애널리스트입니다. 아래는 새로 발표된 AI 모델에 대해 여러 소스에서 자동 수집한 **원본 증거 목록**입니다.

이를 심사위원·개발자가 **10초 안에 요점을 파악**할 수 있는 한국어 리포트로 정리하세요.

# 모델
{model_name}

# 주장(Claims)
{claims}

# 증거(Evidence) — N={n_evidence}건, Source Validator 점수 포함
{evidence}

---

# 리포트 구조 (반드시 아래 섹션 모두 포함, 마크다운)

## ⚡ TL;DR (30초 안에)
- 공식 주장과 커뮤니티 신호의 일치도 한 줄
- 가장 큰 논쟁점 한 줄
- 회의론 신호 유무 한 줄

## 📊 Claim ↔ Evidence 매트릭스
| Claim | 지지 | 반박 | 중립 | Confidence |
|---|---|---|---|---|
| C1 ... | 건수 | 건수 | 건수 | 🟢/🟡/🔴 |

## 🗣️ 핵심 Quote (원문 인용 3~5개)
> "...원문..." — 소스명, 점수, URL

## ⚔️ 대립 구도 (공식 vs 커뮤니티)
- **공식**: "..."
- **커뮤니티**: "..." (건수)
- → 애널리스트 판단 한 줄

## 🔎 회의론 신호
Gary Marcus / AI Snake Oil / Ben Recht 등에서 언급 여부 + 있다면 요지 1~2줄.

## 🎯 Final Assessment
- Confidence: [높음/중간/낮음]
- 근거: 한 줄
- 추천 후속 검증: 한 줄

# 규칙
- 중립 톤, 가치판단 억제. 비판은 원문 인용으로.
- Quote는 원문 그대로 (영어면 영어 + 한국어 요지 한 줄).
- Validator 점수(`validation.aggregate`)를 가중치로 사용. 3.5+는 강한 신호, 2.0 미만은 보조 신호로만.
- 마크다운만 출력, 추가 설명 없이 바로 시작.
"""


def _emit(payload: Any) -> None:
    """Write JSON to stdout with stable encoding; flush to help subprocess parents."""
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _fail(msg: str, code: int = 3) -> None:
    sys.stderr.write(f"ari_agent.cli: {msg}\n")
    sys.stderr.flush()
    sys.exit(code)


def _read_stdin_json() -> dict:
    data = sys.stdin.read()
    if not data.strip():
        _fail("stdin is empty; expected JSON object", code=2)
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        _fail(f"stdin is not valid JSON: {e}", code=2)


def _run_scraper(scrape_fn, input_: ScrapeInput) -> dict:
    result = scrape_fn(input_)
    return {
        "evidence": [it.model_dump() for it in result.items],
        "stats": {
            "source": result.source,
            "ok": result.ok,
            "count": len(result.items),
            "error": result.error,
            "latency_ms": result.latency_ms,
            "fetched_at": result.fetched_at,
        },
    }


# -------- subcommand handlers --------


def cmd_scrape_rss(args: argparse.Namespace) -> None:
    extra: dict[str, Any] = {}
    if args.feed_key:
        extra["feed_key"] = args.feed_key
    if args.feed_url:
        extra["feed_url"] = args.feed_url
    inp = ScrapeInput(query=args.query or "", limit=args.limit, since_days=args.since_days, extra=extra)
    _emit(_run_scraper(s_rss.scrape, inp))


def cmd_scrape_arxiv(args: argparse.Namespace) -> None:
    inp = ScrapeInput(query=args.query, limit=args.limit, since_days=args.since_days)
    _emit(_run_scraper(s_arxiv.scrape, inp))


def cmd_scrape_reddit(args: argparse.Namespace) -> None:
    # --cache-file: load pre-fetched JSON (for Brev/cloud IPs that Reddit 403s).
    # File must match the scrape_reddit output shape: {"evidence":[...],"stats":{...}}.
    # When set, --query/--subreddits/--limit/--since-days are ignored.
    if args.cache_file:
        from pathlib import Path
        try:
            raw = Path(args.cache_file).read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError) as e:
            _fail(f"cache-file read failed: {type(e).__name__}: {e}", code=3)
        stats = payload.get("stats") or {}
        stats.setdefault("source", "reddit")
        stats["cache"] = {"file": args.cache_file, "hit": True}
        _emit({"evidence": payload.get("evidence", []), "stats": stats})
        return
    extra: dict[str, Any] = {}
    if args.subreddits:
        extra["subreddits"] = [s.strip() for s in args.subreddits.split(",") if s.strip()]
    inp = ScrapeInput(query=args.query, limit=args.limit, since_days=args.since_days, extra=extra)
    _emit(_run_scraper(s_reddit.scrape, inp))


def cmd_scrape_hackernews(args: argparse.Namespace) -> None:
    inp = ScrapeInput(query=args.query, limit=args.limit, since_days=args.since_days)
    _emit(_run_scraper(s_hn.scrape, inp))


def cmd_scrape_github(args: argparse.Namespace) -> None:
    extra: dict[str, Any] = {}
    if args.repo:
        extra["repo"] = args.repo
    inp = ScrapeInput(query=args.query, limit=args.limit, since_days=args.since_days, extra=extra)
    _emit(_run_scraper(s_github.scrape, inp))


def cmd_scrape_hf_papers(args: argparse.Namespace) -> None:
    inp = ScrapeInput(query=args.query, limit=args.limit, since_days=args.since_days)
    _emit(_run_scraper(s_hf.scrape, inp))


def cmd_enrich_bodies(args: argparse.Namespace) -> None:
    payload = _read_stdin_json()
    raw_items = payload.get("evidence", [])
    try:
        items = [EvidenceItem.model_validate(it) for it in raw_items]
    except Exception as e:  # noqa: BLE001
        _fail(f"stdin.evidence[*] does not match EvidenceItem: {e}", code=2)
    enriched, stats = enrich_many(items, max_workers=args.workers)
    # EnrichStats is a @dataclass(slots=True); json cannot serialize it directly.
    _emit({
        "evidence": [it.model_dump() for it in enriched],
        "stats": {
            "total": stats.total,
            "enriched": stats.enriched,
            "skipped": stats.skipped,
            "errors": stats.errors,
            "latency_ms": stats.latency_ms,
        },
    })


def cmd_validate_sources(args: argparse.Namespace) -> None:
    payload = _read_stdin_json()
    raw_items = payload.get("evidence", [])
    try:
        items = [EvidenceItem.model_validate(it) for it in raw_items]
    except Exception as e:  # noqa: BLE001
        _fail(f"stdin.evidence[*] does not match EvidenceItem: {e}", code=2)
    validations = validate_many(items)
    _emit({
        "validations": [v.to_dict() for v in validations],
        "stats": {"count": len(validations)},
    })


def _fetch_and_strip(url: str, timeout: int, max_chars: int) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    text = resp.text
    if "<html" in text.lower():
        text = re.sub(r"<script.*?</script>", "", text, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def cmd_extract_claims(args: argparse.Namespace) -> None:
    try:
        content = _fetch_and_strip(args.url, DEFAULT_TIMEOUT_SECONDS, args.max_input_chars)
    except requests.RequestException as e:
        _fail(f"fetch failed: {type(e).__name__}: {e}", code=3)
    prompt = CLAIM_EXTRACTOR_PROMPT.format(content=content)
    try:
        raw = llm_client.call_nemotron(
            system="You are a precise JSON generator. Output only valid JSON.",
            user=prompt,
            tier="nano",
            temperature=0.0,
            max_tokens=2048,
        )
    except Exception as e:  # noqa: BLE001
        _fail(f"LLM call failed: {type(e).__name__}: {e}", code=3)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        parsed = {"model_name": "(parse-failed)", "claims": [], "_error": str(e), "_raw": raw[:1000]}
    _emit(parsed)


def _format_evidence_for_prompt(items: list[dict], top_n: int = 40) -> str:
    def _score(it: dict) -> float:
        return float(((it.get("metadata") or {}).get("validation") or {}).get("aggregate") or 0.0)

    sorted_items = sorted(items, key=_score, reverse=True)[:top_n]
    lines: list[str] = []
    for i, it in enumerate(sorted_items, 1):
        body = (it.get("body_full") or it.get("text") or "").strip().replace("\n", " ")
        body = body[:500] + ("…" if len(body) > 500 else "")
        lines.append(
            f"[{i}] score={_score(it):.2f} src={it.get('source_detail')} author={it.get('author') or '-'} "
            f"ts={it.get('timestamp') or '-'} url={it.get('url')}\n"
            f"  title: {(it.get('title') or '(no title)')[:150]}\n"
            f"  body:  {body}"
        )
    return "\n\n".join(lines)


def cmd_synthesize_report(args: argparse.Namespace) -> None:
    payload = _read_stdin_json()
    claims = payload.get("claims", [])
    evidence = payload.get("evidence", [])
    model_name = payload.get("model_name", args.model_name or "(unspecified)")

    if isinstance(claims, dict) and "claims" in claims:
        claim_items = claims["claims"]
    elif isinstance(claims, list):
        claim_items = claims
    else:
        claim_items = []
    claims_md = "\n".join(
        f"- {c.get('id', f'C{i}')}: {c.get('text', '')}" for i, c in enumerate(claim_items, 1)
    )

    prompt = SYNTHESIZER_PROMPT.format(
        model_name=model_name,
        claims=claims_md or "(no claims provided)",
        n_evidence=len(evidence),
        evidence=_format_evidence_for_prompt(evidence, top_n=args.top_n),
    )
    try:
        markdown = llm_client.call_nemotron(
            system=SYNTHESIZER_SYSTEM,
            user=prompt,
            tier="super",
            temperature=0.2,
            max_tokens=args.max_tokens,
        )
    except Exception as e:  # noqa: BLE001
        _fail(f"LLM call failed: {type(e).__name__}: {e}", code=3)
    _emit({"markdown": markdown, "stats": {"n_evidence": len(evidence), "n_claims": len(claim_items)}})


def cmd_health(_args: argparse.Namespace) -> None:
    _emit({"ok": True, "llm": llm_client.describe()})


# -------- arg parsing --------


def _base_scrape_args(p: argparse.ArgumentParser, require_query: bool = True) -> None:
    p.add_argument("--query", required=require_query, help="Primary search phrase")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--since-days", type=int, default=30)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ari_agent.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scrape_rss")
    _base_scrape_args(p, require_query=False)
    p.add_argument("--feed-key")
    p.add_argument("--feed-url")
    p.set_defaults(func=cmd_scrape_rss)

    p = sub.add_parser("scrape_arxiv")
    _base_scrape_args(p)
    p.set_defaults(func=cmd_scrape_arxiv)

    p = sub.add_parser("scrape_reddit")
    _base_scrape_args(p, require_query=False)  # query optional so --cache-file alone works
    p.add_argument("--subreddits", help="Comma-separated list, e.g. 'LocalLLaMA,MachineLearning'")
    p.add_argument(
        "--cache-file",
        help="Load pre-fetched evidence JSON from this path (bypasses HTTP; "
        "for cloud IPs that Reddit 403s). See docs/cache/reddit-*.json.",
    )
    p.set_defaults(func=cmd_scrape_reddit)

    p = sub.add_parser("scrape_hackernews")
    _base_scrape_args(p)
    p.set_defaults(func=cmd_scrape_hackernews)

    p = sub.add_parser("scrape_github")
    _base_scrape_args(p)
    p.add_argument("--repo", help="Pin to a single repo, e.g. 'anthropics/anthropic-sdk-python'")
    p.set_defaults(func=cmd_scrape_github)

    p = sub.add_parser("scrape_hf_papers")
    _base_scrape_args(p)
    p.set_defaults(func=cmd_scrape_hf_papers)

    p = sub.add_parser("enrich_bodies")
    p.add_argument("--workers", type=int, default=5)
    p.set_defaults(func=cmd_enrich_bodies)

    p = sub.add_parser("validate_sources")
    p.set_defaults(func=cmd_validate_sources)

    p = sub.add_parser("extract_claims")
    p.add_argument("--url", required=True)
    p.add_argument("--max-input-chars", type=int, default=8000)
    p.set_defaults(func=cmd_extract_claims)

    p = sub.add_parser("synthesize_report")
    p.add_argument("--model-name", help="Display name for the model being analyzed")
    p.add_argument("--top-n", type=int, default=40, help="Top-N evidence items by validator score")
    p.add_argument("--max-tokens", type=int, default=6000)
    p.set_defaults(func=cmd_synthesize_report)

    p = sub.add_parser("health")
    p.set_defaults(func=cmd_health)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
