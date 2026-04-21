"""벤치마크 수집 결과 Pydantic 모델."""

from __future__ import annotations

from pydantic import BaseModel


class BenchmarkItem(BaseModel):
    """단일 벤치마크 점수 한 건."""

    name: str
    score: float | None
    score_str: str
    source: str


class HFDiscussionComment(BaseModel):
    """HuggingFace 토론의 댓글 한 건."""

    author: str
    text: str
    created_at: str


class HFDiscussion(BaseModel):
    """HuggingFace 모델 페이지의 토론 한 건 (본문 + 댓글 포함)."""

    title: str
    num: int
    author: str
    created_at: str
    status: str
    num_comments: int
    url: str
    body: str
    comments: list[HFDiscussionComment]


class BenchmarkResult(BaseModel):
    """search_benchmarks 툴의 최종 반환값. JSON 직렬화 대상."""

    model_name: str
    provider: str
    benchmarks: list[BenchmarkItem]
    sources: list[str]
    hf_discussions: list[HFDiscussion] = []
