"""query-generator 에이전트의 Pydantic 데이터 모델."""

from pydantic import BaseModel


class QueryGeneratorOutput(BaseModel):
    """query-generator 에이전트의 출력 모델.

    LLM이 추출한 AI 프러덕트/모델명 목록을 담는다.
    """

    product_names: list[str]
