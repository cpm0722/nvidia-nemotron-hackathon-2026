"""Artificial Analysis 스크래퍼.

https://artificialanalysis.ai/models 페이지에 포함된 Next.js RSC flight 청크를
파싱해 전체 모델 목록과 벤치마크 점수를 추출한다 (API 키 불필요).
"""

from __future__ import annotations

import json
import re
from typing import Optional

import httpx

TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

BASE_URL = "https://artificialanalysis.ai"

# 원시값이 0~1 범위인 필드 → ×100 해서 퍼센트로 표시
PERCENT_FIELDS = {
    "gpqa", "hle", "humaneval", "aime", "aime25",
    "math_500", "mmlu_pro", "mmmu_pro", "livecodebench",
    "scicode", "ifbench", "tau2", "terminalbench_hard", "lcr",
}

# 수집할 벤치마크 필드명 → 표시명
BENCHMARK_FIELDS = {
    "intelligence_index": "Intelligence Index",
    "coding_index": "Coding Index",
    "math_index": "Math Index",
    "agentic_index": "Agentic Index",
    "omniscience": "Omniscience",
    "gpqa": "GPQA Diamond",
    "hle": "HLE",
    "humaneval": "HumanEval",
    "aime": "AIME 2024",
    "aime25": "AIME 2025",
    "math_500": "MATH-500",
    "mmlu_pro": "MMLU-Pro",
    "mmmu_pro": "MMMU-Pro",
    "livecodebench": "LiveCodeBench",
    "scicode": "SciCode",
    "tau2": "TAU-2",
    "ifbench": "IFBench",
    "lcr": "LCR",
    "terminalbench_hard": "TerminalBench (Hard)",
    "gdpval": "GDPVal",
    "critpt": "CritPT",
}


def _normalize(s: str) -> str:
    return re.sub(r"[\s\-_.]", "", s).lower()


def _find_models_array(obj: object, depth: int = 0) -> Optional[list]:
    """JSON 트리에서 slug + intelligence_index 필드를 가진 models 배열을 재귀 탐색한다."""
    if depth > 30:
        return None
    if isinstance(obj, dict):
        if "models" in obj and isinstance(obj["models"], list):
            models = obj["models"]
            if len(models) > 10 and any(
                isinstance(m, dict) and "slug" in m and "intelligence_index" in m
                for m in models[:5]
            ):
                return models
        for v in obj.values():
            result = _find_models_array(v, depth + 1)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_models_array(item, depth + 1)
            if result is not None:
                return result
    return None


def _parse_rsc_chunks(html: str) -> Optional[list]:
    """HTML에서 Next.js RSC flight 청크를 추출하고 models 배열을 반환한다.

    RSC 청크 형식: self.__next_f.push([1,"KEY:JSON"])
    """
    pattern = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')

    for match in pattern.finditer(html):
        raw = match.group(1)
        try:
            decoded = json.loads('"' + raw + '"')
        except Exception:
            continue

        colon_idx = decoded.find(":")
        if colon_idx == -1:
            continue
        json_part = decoded[colon_idx + 1:]

        if '"models"' not in json_part or '"slug"' not in json_part:
            continue

        try:
            data = json.loads(json_part)
        except Exception:
            continue

        models = _find_models_array(data)
        if models:
            return models

    return None


def _extract_benchmarks_from_model(model: dict) -> list[dict]:
    """AA 모델 딕셔너리에서 벤치마크 점수를 추출한다."""
    benchmarks = []
    for field, display_name in BENCHMARK_FIELDS.items():
        val = model.get(field)
        if val is None:
            continue
        try:
            score = float(val)
        except (TypeError, ValueError):
            continue
        if field in PERCENT_FIELDS:
            score = round(score * 100, 2)
            score_str = f"{score:.1f}%"
        else:
            score_str = f"{score:.2f}".rstrip("0").rstrip(".")
        benchmarks.append({"name": display_name, "score": score, "score_str": score_str})
    return benchmarks


def fetch_model_benchmarks(model_name: str) -> tuple[list[dict], str, str]:
    """모델명으로 AA 전체 모델 목록을 검색해 벤치마크를 반환한다.

    Args:
        model_name: 검색할 모델명.

    Returns:
        (benchmarks, 매칭된_모델명, provider)
    """
    try:
        r = httpx.get(f"{BASE_URL}/models", headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            print(f"[ArtificialAnalysis] HTTP {r.status_code}")
            return [], "", ""
    except Exception as e:
        print(f"[ArtificialAnalysis] 요청 실패: {e}")
        return [], "", ""

    models = _parse_rsc_chunks(r.text)
    if not models:
        return [], "", ""

    query = _normalize(model_name)
    best_model: Optional[dict] = None
    best_score = -1

    for m in models:
        if not isinstance(m, dict):
            continue
        name_n = _normalize(m.get("name") or "")
        slug_n = _normalize(m.get("slug") or "")

        if query == name_n or query == slug_n:
            best_model = m
            break

        score = 0.0
        if query in name_n or name_n in query:
            score = 1.0 + len(query) / max(len(name_n), 1)
        elif query in slug_n or slug_n in query:
            score = 0.5

        if score > best_score:
            best_score = score
            best_model = m

    if not best_model or best_score <= 0:
        return [], "", ""

    creator = best_model.get("model_creators") or {}
    provider = creator.get("name", "") if isinstance(creator, dict) else ""
    model_display = best_model.get("name") or best_model.get("slug") or model_name
    return _extract_benchmarks_from_model(best_model), model_display, provider
