"""LLM이 반환한 JSON 배열 문자열을 QueryGeneratorOutput으로 파싱하는 유틸리티."""

import json
import re

from nat_query_generator.models import QueryGeneratorOutput


def parse_product_names(llm_output: str) -> QueryGeneratorOutput:
    """LLM 응답 문자열에서 AI 프러덕트/모델명 목록을 파싱한다.

    JSON 배열 형태의 문자열을 받아 QueryGeneratorOutput으로 변환한다.
    마크다운 코드블록(```json ... ``` 또는 ``` ... ```)이 포함된 경우 자동으로 제거한다.

    Args:
        llm_output: LLM이 반환한 원시 문자열. JSON 배열 형태를 기대한다.

    Returns:
        파싱된 QueryGeneratorOutput 인스턴스.

    Raises:
        ValueError: JSON 배열로 파싱할 수 없거나, 배열 원소가 문자열이 아닌 경우.
    """
    text = llm_output.strip()

    # ```json ... ``` 또는 ``` ... ``` 코드블록에서 내용 추출
    code_block_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM output is not valid JSON: {llm_output!r}") from e

    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got {type(parsed).__name__}: {llm_output!r}")

    if not all(isinstance(item, str) for item in parsed):
        raise ValueError(f"Expected array of strings, got mixed types: {llm_output!r}")

    return QueryGeneratorOutput(product_names=parsed)
