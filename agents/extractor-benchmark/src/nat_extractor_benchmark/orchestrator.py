"""벤치마크 수집 오케스트레이터.

AA와 HF 스크래퍼를 호출해 결과를 합산한 뒤 BenchmarkResult로 반환한다.
"""

from __future__ import annotations

from nat_extractor_benchmark.models import (
    BenchmarkItem,
    BenchmarkResult,
    HFDiscussion,
    HFDiscussionComment,
)
from nat_extractor_benchmark.scrapers.artificialanalysis import (
    fetch_model_benchmarks as _aa_fetch,
)
from nat_extractor_benchmark.scrapers.huggingface import (
    fetch_benchmarks_for_model as _hf_fetch,
    fetch_discussions as _hf_discussions,
)


def collect_benchmarks(
    model_name: str,
    discussion_limit: int = 10,
    comment_limit: int = 3,
) -> BenchmarkResult:
    """AA + HF 벤치마크와 HF 토론을 수집해 BenchmarkResult를 반환한다.

    Args:
        model_name: 조회할 LLM 모델명.
        discussion_limit: 가져올 HF 토론 수.
        comment_limit: 각 토론당 댓글 수 상한.

    Returns:
        BenchmarkResult (두 소스 합산, 중복 벤치마크명 제거, AA 우선).
    """
    print(f"[Benchmark] '{model_name}' 조회 시작")

    # --- Artificial Analysis ---
    aa_bm, aa_name, aa_provider = _aa_fetch(model_name)
    aa_items = [
        BenchmarkItem(
            name=b["name"],
            score=b.get("score"),
            score_str=b["score_str"],
            source="Artificial Analysis",
        )
        for b in aa_bm
    ]
    if aa_items:
        print(f"[Benchmark] AA 히트: {aa_name} ({len(aa_items)}개)")
    else:
        print(f"[Benchmark] AA 데이터 없음: {model_name}")

    # --- HuggingFace ---
    hf_bm, hf_name, hf_provider, hf_model_id = _hf_fetch(model_name)
    hf_items = [
        BenchmarkItem(
            name=b["name"],
            score=b.get("score"),
            score_str=b["score_str"],
            source="HuggingFace",
        )
        for b in hf_bm
    ]
    if hf_items:
        print(f"[Benchmark] HF 히트: {hf_name} ({len(hf_items)}개)")
    else:
        print(f"[Benchmark] HF 데이터 없음: {model_name}")

    # --- 합산 (AA 우선, 중복 벤치마크명 스킵) ---
    combined: list[BenchmarkItem] = []
    seen_names: set[str] = set()
    for item in aa_items + hf_items:
        key = item.name.lower()
        if key not in seen_names:
            combined.append(item)
            seen_names.add(key)

    model_display = aa_name or hf_name or model_name
    provider = aa_provider or hf_provider or ""
    sources = sorted({item.source for item in combined})

    # --- HuggingFace 토론 ---
    discussions: list[HFDiscussion] = []
    if hf_model_id:
        raw_discussions = _hf_discussions(
            hf_model_id,
            limit=discussion_limit,
            comment_limit=comment_limit,
        )
        for d in raw_discussions:
            discussions.append(
                HFDiscussion(
                    title=d.get("title", ""),
                    num=d.get("num") or 0,
                    author=d.get("author", ""),
                    created_at=d.get("created_at", ""),
                    status=d.get("status", ""),
                    num_comments=d.get("num_comments", 0),
                    url=d.get("url", ""),
                    body=d.get("body", ""),
                    comments=[
                        HFDiscussionComment(
                            author=c.get("author", ""),
                            text=c.get("text", ""),
                            created_at=c.get("created_at", ""),
                        )
                        for c in d.get("comments", [])
                    ],
                )
            )
        if discussions:
            print(f"[Benchmark] HF 토론 {len(discussions)}개 조회")

    return BenchmarkResult(
        model_name=model_display,
        provider=provider,
        benchmarks=combined,
        sources=sources,
        hf_discussions=discussions,
    )
