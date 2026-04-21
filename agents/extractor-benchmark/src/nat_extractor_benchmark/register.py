"""NAT function group 등록: LLM 벤치마크 수집기를 search_benchmarks 툴로 노출한다."""

import asyncio
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from nat_extractor_benchmark.models import BenchmarkResult
from nat_extractor_benchmark.orchestrator import collect_benchmarks


class BenchmarkExtractorConfig(FunctionGroupBaseConfig, name="benchmark_extractor"):
    """LLM 벤치마크 추출기 function group 설정.

    Args:
        discussion_limit: 가져올 HuggingFace 토론 수.
        comment_limit: 각 토론당 댓글 수 상한.
        include: NAT에 노출할 함수 이름 목록.
    """

    discussion_limit: int = Field(default=10, description="Max HuggingFace discussions to fetch")
    comment_limit: int = Field(default=3, description="Max comments per HuggingFace discussion")
    include: list[str] = Field(default_factory=lambda: ["search_benchmarks"])


@register_function_group(config_type=BenchmarkExtractorConfig)
async def benchmark_extractor_group(
    config: BenchmarkExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """벤치마크 수집기 function group을 생성·등록한다.

    search_benchmarks 툴 하나를 노출하며, 동기 스크래퍼를 asyncio.to_thread로
    실행해 이벤트 루프 블로킹을 방지한다.

    Args:
        config: 벤치마크 추출기 설정 (discussion_limit, comment_limit).
        _builder: 워크플로우 빌더 (미사용).

    Yields:
        FunctionGroup containing the search_benchmarks tool.
    """
    group = FunctionGroup(config=config)

    async def search_benchmarks(model_name: str) -> str:
        """LLM 모델의 벤치마크 점수와 HuggingFace 사용자 토론을 수집한다.

        Artificial Analysis와 HuggingFace 모델 카드에서 벤치마크 점수를,
        HuggingFace 모델 페이지에서 최신 토론(본문 + 댓글)을 조회해 합산한 JSON을 반환한다.
        두 소스에서 동일한 벤치마크명이 겹치면 Artificial Analysis를 우선한다.

        Args:
            model_name: 조회할 LLM 모델명 (e.g. "gemma 3", "claude opus 4.7", "gpt-5").

        Returns:
            BenchmarkResult JSON (model_name, provider, benchmarks, sources, hf_discussions).
        """
        result: BenchmarkResult = await asyncio.to_thread(
            collect_benchmarks,
            model_name,
            config.discussion_limit,
            config.comment_limit,
        )
        return result.model_dump_json(indent=2)

    group.add_function(
        name="search_benchmarks",
        fn=search_benchmarks,
        description=search_benchmarks.__doc__,
    )
    yield group
