"""NAT function group: E2E pipeline orchestrator.

query-generator → extractors[7] (병렬) → reporter 순서로 A2A 호출을 조율하며
generate_queries / collect_evidence / generate_report 세 툴을 노출한다.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

import requests
from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig


class E2EPipelineConfig(FunctionGroupBaseConfig, name="e2e_pipeline"):
    """E2E pipeline orchestrator function group 설정.

    Args:
        query_generator_url: query-generator A2A 서버 URL.
        extractor_urls: extractor A2A 서버 URL 목록 (병렬 호출).
        reporter_url: reporter A2A 서버 URL.
        timeout_seconds: 각 A2A 호출당 타임아웃(초).
        include: NAT에 노출할 함수 이름 목록.
    """

    query_generator_url: str = Field(default="http://localhost:10001")
    extractor_urls: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:10010",
            "http://localhost:10011",
            "http://localhost:10012",
            "http://localhost:10013",
            "http://localhost:10014",
            "http://localhost:10015",
            "http://localhost:10016",
        ]
    )
    reporter_url: str = Field(default="http://localhost:10002")
    timeout_seconds: int = Field(default=180, ge=30, le=600)
    include: list[str] = Field(
        default_factory=lambda: ["generate_queries", "collect_evidence", "generate_report"]
    )


def _a2a_send(url: str, message: str, timeout: int) -> str:
    """A2A 서버에 message를 보내고 응답 텍스트를 반환한다."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "id": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
        },
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    artifacts = data.get("result", {}).get("artifacts", [])
    if not artifacts:
        return ""
    parts = artifacts[0].get("parts", [])
    return parts[0].get("text", "") if parts else ""


@register_function_group(config_type=E2EPipelineConfig)
async def e2e_pipeline_group(
    config: E2EPipelineConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """E2E pipeline function group을 생성·등록한다.

    generate_queries / collect_evidence / generate_report 세 툴을 노출하며,
    각 툴은 내부적으로 A2A 호출로 위임한다. collect_evidence는 asyncio.gather로
    모든 extractor를 병렬 실행한다.

    Args:
        config: 파이프라인 설정 (URL 목록, 타임아웃).
        _builder: 워크플로우 빌더 (미사용).

    Yields:
        FunctionGroup containing the three pipeline tools.
    """
    group = FunctionGroup(config=config)

    async def generate_queries(user_query: str) -> str:
        """사용자 자연어 쿼리에서 AI 제품명 목록을 추출한다.

        query-generator A2A 서버를 호출해 검색 가능한 영어 제품명 배열을 반환한다.

        Args:
            user_query: 한국어 또는 영어 자연어 쿼리
                        (예: "GPT5와 Gemma4 비교해줘").

        Returns:
            JSON 배열 문자열 (예: '["GPT 5", "Gemma 4"]').
            파싱 실패 시 원본 응답 문자열 그대로 반환.
        """
        result = await asyncio.to_thread(
            _a2a_send, config.query_generator_url, user_query, config.timeout_seconds
        )
        return result

    async def _call_extractor(url: str, product_name: str, timeout: int) -> dict:
        """단일 extractor A2A 서버를 호출하고 ScrapeResult dict를 반환한다.

        실패 시 ok=False인 빈 ScrapeResult dict를 반환해 전체 파이프라인을 중단시키지 않는다.
        """
        try:
            raw = await asyncio.to_thread(_a2a_send, url, product_name, timeout)
            return json.loads(raw)
        except Exception as exc:
            return {"source": url, "ok": False, "items": [], "error": str(exc)}

    async def collect_evidence(product_name: str) -> str:
        """7개 extractor에서 병렬로 evidence를 수집한다.

        각 extractor A2A 서버를 asyncio.gather로 동시에 호출하며, 개별 실패는
        ok=False 항목으로 기록하고 나머지 결과를 반환한다.

        Args:
            product_name: 검색할 AI 제품명 (예: "GPT 5", "Gemma 4").

        Returns:
            ScrapeResult 객체 배열의 JSON 문자열.
            각 원소는 {source, ok, items[], error, latency_ms} 형태.
        """
        tasks = [
            _call_extractor(url, product_name, config.timeout_seconds)
            for url in config.extractor_urls
        ]
        results = await asyncio.gather(*tasks)
        return json.dumps(list(results), ensure_ascii=False, indent=2, default=str)

    async def generate_report(evidence_input: str) -> str:
        """수집된 evidence를 reporter에 전달해 최종 보고서를 생성한다.

        Args:
            evidence_input: "Product: <name>\\n\\nEvidence:\\n<JSON>" 형식 문자열.
                            collect_evidence 결과를 포함해야 한다.

        Returns:
            구조화된 마크다운 보고서 문자열.
            reporter 호출 실패 시 오류 메시지 반환.
        """
        try:
            result = await asyncio.to_thread(
                _a2a_send, config.reporter_url, evidence_input, config.timeout_seconds
            )
            return result
        except Exception as exc:
            return f"Reporter error: {exc}"

    group.add_function(
        name="generate_queries",
        fn=generate_queries,
        description=generate_queries.__doc__,
    )
    group.add_function(
        name="collect_evidence",
        fn=collect_evidence,
        description=collect_evidence.__doc__,
    )
    group.add_function(
        name="generate_report",
        fn=generate_report,
        description=generate_report.__doc__,
    )
    yield group
