"""NAT function group 등록: LLM 벤치마크 수집기를 search_benchmarks 툴로 노출한다."""

import json
from collections.abc import AsyncGenerator

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig

from ari_core import run_scraper_async
from nat_extractor_benchmark.scraper import scrape as _scrape_benchmark


class BenchmarkExtractorConfig(FunctionGroupBaseConfig, name="benchmark_extractor"):
    """LLM 벤치마크 추출기 function group 설정.

    Args:
        default_limit: 반환할 총 EvidenceItem 최대 개수. AA 1건 + HF 벤치마크 1건 뒤에
            남은 슬롯을 HF 토론으로 채운다.
        comment_limit: 각 HF 토론당 댓글 수 상한.
        include: NAT에 노출할 함수 이름 목록.
    """

    default_limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum total EvidenceItems (AA + HF benchmark + HF discussions)",
    )
    comment_limit: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Maximum comments per HuggingFace discussion",
    )
    include: list[str] = Field(default_factory=lambda: ["search_benchmarks"])


@register_function_group(config_type=BenchmarkExtractorConfig)
async def benchmark_extractor_group(
    config: BenchmarkExtractorConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """벤치마크 수집기 function group을 생성·등록한다.

    search_benchmarks 툴 하나를 노출하며, ari_core의 run_scraper_async를 통해
    동기 스크래퍼를 비동기로 실행한다.

    Args:
        config: 벤치마크 추출기 설정 (default_limit, comment_limit).
        _builder: 워크플로우 빌더 (미사용).

    Yields:
        FunctionGroup containing the search_benchmarks tool.
    """
    group = FunctionGroup(config=config)

    async def search_benchmarks(model_name: str) -> str:
        """LLM 모델의 벤치마크 점수와 HuggingFace 사용자 토론을 수집한다.

        Artificial Analysis와 HuggingFace 모델 카드에서 벤치마크 점수를,
        HuggingFace 모델 페이지에서 최신 토론(본문 + 댓글)을 조회하고,
        HuggingFace 모델 카드 README.md 원문을 body_full에 담아 반환한다.
        결과는 ari_core.EvidenceItem으로 정규화된 ScrapeResult JSON.

        Args:
            model_name: 조회할 LLM 모델명 (e.g. "gemma 3", "claude opus 4.7", "gpt-5").

        Returns:
            ScrapeResult JSON 문자열 (source, ok, items[], latency_ms 필드 포함).
            items는 AA 벤치마크(0~1건), HF 벤치마크+카드(0~1건), HF 토론(N건) 순.
        """
        extra = {"comment_limit": config.comment_limit}
        result = await run_scraper_async(
            _scrape_benchmark,
            query=model_name,
            limit=config.default_limit,
            extra=extra,
        )
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)

    group.add_function(
        name="search_benchmarks",
        fn=search_benchmarks,
        description=search_benchmarks.__doc__,
    )
    yield group
