"""NAT function group: validator_caller — calls the validator A2A agent to filter scraped results."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import requests
from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.data_models.function import FunctionGroupBaseConfig


class ValidatorCallerConfig(FunctionGroupBaseConfig, name="validator_caller"):
    """validator_caller function group 설정.

    Extractor들이 이 function group을 등록해 validation tool로 사용한다.

    Args:
        url: 실행 중인 validator A2A 서버 URL.
        system_prompt_file: 소스별 validation criteria 파일 경로 (CWD 기준).
        timeout_seconds: validator A2A 호출 타임아웃 (초).
        include: NAT에 노출할 함수 이름 목록.
    """

    url: str = Field(default="http://localhost:10010", description="Validator A2A server URL")
    system_prompt_file: str = Field(
        default="prompts/validator_system_prompt.txt",
        description="Path to source-specific validation criteria file (relative to CWD)",
    )
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    include: list[str] = Field(default_factory=lambda: ["validate"])


def _a2a_send(url: str, message: str, timeout: int) -> str:
    """validator A2A 서버에 tasks/send 요청을 보내고 응답 텍스트를 반환한다.

    Args:
        url: validator A2A 서버 base URL (e.g. "http://localhost:10010").
        message: 전송할 user message 텍스트.
        timeout: HTTP 요청 타임아웃 (초).

    Returns:
        A2A 응답의 첫 번째 artifact 텍스트. 응답 파싱 실패 시 빈 문자열.
    """
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
    if not parts:
        return ""
    return parts[0].get("text", "")


@register_function_group(config_type=ValidatorCallerConfig)
async def validator_caller_group(
    config: ValidatorCallerConfig, _builder: Builder
) -> AsyncGenerator[FunctionGroup, None]:
    """validator_caller function group을 생성·등록한다.

    validate 툴 하나를 노출하며, 동기 HTTP 호출을 asyncio.to_thread로 실행해
    이벤트 루프 블로킹을 방지한다.

    Args:
        config: validator URL, criteria 파일 경로, 타임아웃 설정.
        _builder: 워크플로우 빌더 (미사용).

    Yields:
        FunctionGroup containing the validate tool.
    """
    group = FunctionGroup(config=config)

    async def validate(product_name: str, scraped_json: str) -> str:
        """수집된 결과를 validator A2A 에이전트로 검증·필터링한다.

        소스별 validation criteria와 scraped_json을 validator에 전달해
        관련성 없는 항목을 제거한 ScrapeResult JSON을 반환한다.

        Args:
            product_name: 검색한 AI 프러덕트 이름 (e.g. "GPT-5", "Claude 4").
            scraped_json: 검증할 ScrapeResult JSON 문자열.

        Returns:
            필터링된 ScrapeResult JSON 문자열.
        """
        criteria_path = Path(config.system_prompt_file)
        criteria = criteria_path.read_text(encoding="utf-8") if criteria_path.exists() else ""

        message = (
            f"Product: {product_name}\n\n"
            f"Source criteria:\n{criteria}\n\n"
            f"Scraped data:\n{scraped_json}"
        )

        try:
            result_text = await asyncio.to_thread(
                _a2a_send, config.url, message, config.timeout_seconds
            )
            # 응답이 유효한 JSON인지 확인 후 반환, 실패 시 원본 반환
            json.loads(result_text)
            return result_text
        except Exception:  # noqa: BLE001
            return scraped_json

    group.add_function(name="validate", fn=validate, description=validate.__doc__)
    yield group
