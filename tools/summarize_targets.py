"""Brev-hosted Nemotron-3-Super로 타깃별 raw evidence를 사람이 보기 좋은
한국어 요약으로 변환하는 스크립트.

엔드포인트: https://model-server-uya78rbya.brevlab.com/v1/ (OpenAI-compatible, no auth)
모델: nvidia/nemotron-3-super-120b-a12b (vLLM, 262K context)

Usage:
    cd src && PYTHONPATH=. python3 tools/summarize_targets.py

산출물:
    docs/summary-claude-opus-4.7.md
    docs/summary-nemotron-3-super.md
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_ROOT = HERE.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openai import OpenAI

from ari_agent.enrichers.body_fetcher import enrich_many  # noqa: E402
from ari_agent.schemas import EvidenceItem  # noqa: E402
from ari_agent.validators.source_validator import validate_many  # noqa: E402
from tools.generate_target_reports import TARGETS, gather  # noqa: E402

REPO_ROOT = SRC_ROOT.parent
DOCS_DIR = REPO_ROOT / "docs"

BREV_ENDPOINT = os.getenv(
    "NEMOTRON_BASE_URL",
    "https://model-server-uya78rbya.brevlab.com/v1/",
)
MODEL = "nvidia/nemotron-3-super-120b-a12b"


SUMMARY_PROMPT = """당신은 AI 모델 릴리즈를 평가하는 리서치 애널리스트입니다. 아래는 새로 발표된 AI 모델에 대해 여러 소스에서 자동 수집한 **원본 증거 목록**입니다.

이를 심사위원·개발자가 **10초 안에 요점을 파악**할 수 있는 한국어 리포트로 정리하세요.

# 모델
{model_name}

# 주장(Claims) — 공식 발표에서 추출
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
- 중립 톤, 가치판단 억제. 비판은 원문 인용으로 전달.
- Quote는 원문 그대로 (영어 원문이면 영어 그대로 + 한국어 요지 한 줄).
- Validator 점수(`validation.aggregate`)를 가중치로 사용. 3.5+는 강한 신호, 2.0 미만은 보조 신호로만.
- 답변은 마크다운만 출력, 추가 설명 없이 바로 시작.
"""


def format_evidence_for_prompt(items: list[EvidenceItem]) -> str:
    """프롬프트 크기 제어를 위해 점수순 상위 항목만 뽑아 컴팩트하게 직렬화."""

    def _score(it: EvidenceItem) -> float:
        return float(((it.metadata or {}).get("validation") or {}).get("aggregate") or 0.0)

    sorted_items = sorted(items, key=_score, reverse=True)[:40]
    lines: list[str] = []
    for i, it in enumerate(sorted_items, 1):
        score = _score(it)
        body = (it.body_full or it.text or "").strip().replace("\n", " ")
        body = body[:500] + ("…" if len(body) > 500 else "")
        lines.append(
            f"[{i}] score={score:.2f} src={it.source_detail} author={it.author or '-'} "
            f"ts={it.timestamp or '-'} url={it.url}\n"
            f"  title: {(it.title or '(no title)')[:150]}\n"
            f"  body:  {body}"
        )
    return "\n\n".join(lines)


# Hand-written claims — 모의 claim_extractor 결과. 실제 production은 LLM으로 교체.
CLAIMS = {
    "claude-opus-4.7": [
        {"id": "C1", "text": "Opus 4.6 대비 agentic coding (SWE-bench 계열) 개선"},
        {"id": "C2", "text": "200K context 장기 reasoning에서 regression 감소"},
        {"id": "C3", "text": "Tool-use 안정성 향상 (MCP/function calling)"},
        {"id": "C4", "text": "SDK 0.96.0에서 token budgets / user_profiles 도입"},
    ],
    "nemotron-3-super": [
        {"id": "C1", "text": "120B / 12B active Hybrid Mamba-Transformer + LatentMoE"},
        {"id": "C2", "text": "enterprise agentic workflow 특화 tool calling"},
        {"id": "C3", "text": "1M 토큰 context window"},
        {"id": "C4", "text": "thinking-mode 예산 최대 16,384 토큰"},
    ],
}


def summarize(target_id: str, client: OpenAI) -> str:
    cfg = TARGETS[target_id]
    print(f"\n=== {cfg['display_name']} ===")
    print("  [1/4] 소스 수집...")
    raw = gather(target_id, cfg)

    print("  [2/4] 본문 보강(trafilatura)...")
    all_items: list[EvidenceItem] = []
    for results in raw.values():
        for r in results:
            all_items.extend(r.items)
    enriched, _ = enrich_many(all_items, max_workers=5)

    print("  [3/4] Source Validator 점수화...")
    validations = validate_many(enriched)
    for it, v in zip(enriched, validations):
        it.metadata.setdefault("validation", {}).update(v.to_dict())

    print(f"  [4/4] Nemotron-3-Super 요약 호출 ({len(enriched)}건 중 상위 40건 전달)...")
    prompt = SUMMARY_PROMPT.format(
        model_name=cfg["display_name"],
        claims="\n".join(f"- {c['id']}: {c['text']}" for c in CLAIMS[target_id]),
        n_evidence=len(enriched),
        evidence=format_evidence_for_prompt(enriched),
    )
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "당신은 중립적인 리서치 애널리스트입니다. 사고 과정을 출력하지 말고 최종 마크다운 리포트만 바로 출력하세요."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=6000,
        # Nemotron thinking mode 비활성화 (vLLM에서 chat_template_kwargs로 전달)
        # 온보딩 가이드: enable_thinking=false 설정하면 사고 토큰 미생성
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    elapsed = time.perf_counter() - t0
    content = resp.choices[0].message.content or ""
    usage = resp.usage
    print(f"      ✓ {elapsed:.1f}s · input={usage.prompt_tokens} tok · output={usage.completion_tokens} tok")
    return content


def main() -> int:
    client = OpenAI(base_url=BREV_ENDPOINT, api_key="unused-but-required")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    for target_id in TARGETS:
        summary = summarize(target_id, client)
        path = DOCS_DIR / f"summary-{target_id}.md"
        header = (
            f"> 모델: `{MODEL}` via `{BREV_ENDPOINT}` (Brev 호스팅 vLLM)\n"
            f"> 생성: 2026-04-21 · 본 리포트는 NIM 호출 없이 Brev 엔드포인트 직호출로 생성\n\n---\n\n"
        )
        path.write_text(header + summary, encoding="utf-8")
        print(f"  ✅ 저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
