# NeMo Agent Toolkit (NAT) 가이드

이 문서는 본 프로젝트에서 NeMo Agent Toolkit(NAT)을 사용해 에이전트를 구현할 때 참고하는 기준 문서다.
A2A 프로토콜을 준수하며, 각 에이전트의 산출물은 `config.yml`로 정의한다.

---

## 환경 설정

- Python 3.11 / 3.12 / 3.13
- 패키지 매니저: `uv` (권장)
- NAT 버전: 1.5.0 (2026년 4월 기준)

```bash
uv add nvidia-nat
uv add "nvidia-nat[langchain]"  # LangChain 기반 툴 필요 시
```

CLI 진입점: `nat`

---

## Backbone 모델

| 모델 | 총 파라미터 | 활성 파라미터 | 용도 |
|------|------------|--------------|------|
| `nvidia/nemotron-3-nano-30b-a3b` | 31.6B | 3.2B (MoE) | 경량·빠른 응답 |
| `nvidia/nemotron-3-super-120b-a12b` | 120B | 12B (LatentMoE) | 복잡한 추론 |

**공통 특징**: Thinking Mode, Inference-Time Budget Control, hybrid Mamba-Transformer MoE

### NIM API 엔드포인트

```
Cloud: https://integrate.api.nvidia.com/v1
Local: http://localhost:8000/v1
Auth:  Bearer nvapi-xxxx
```

---

## config.yml 구조 (에이전트 산출물 표준)

각 에이전트는 `config.yml` 하나로 완전히 정의된다. 아래 구조를 기준으로 작성한다.

```yaml
llms:
  primary_llm:
    _type: nim
    model_name: nvidia/nemotron-3-super-120b-a12b
    temperature: 0.1
    max_tokens: 4096

  fast_llm:
    _type: nim
    model_name: nvidia/nemotron-3-nano-30b-a3b
    temperature: 0.0
    max_tokens: 2048

functions:
  # 사용할 툴을 여기에 선언
  wiki_search:
    _type: wiki_search

  tavily_search:
    _type: tavily_internet_search

  # MCP 클라이언트 툴 그룹 예시
  mcp_tools:
    _type: mcp_client
    server:
      transport: streamable-http
      url: http://localhost:9000

workflow:
  _type: react_agent
  llm_name: primary_llm
  tool_names:
    - wiki_search
    - tavily_search
  verbose: true
```

### `_type` 레퍼런스

**llms**
| `_type` | 설명 |
|---------|------|
| `nim` | NVIDIA NIM (기본값) |
| `openai` | OpenAI API |
| `anthropic` | Anthropic API |
| `ollama` | 로컬 Ollama |

**workflow (에이전트 종류)**
| `_type` | 설명 |
|---------|------|
| `react_agent` | Reasoning + Acting 루프 에이전트 |
| `auto_memory_agent` | 세션 간 메모리 유지 에이전트 |
| `langgraph_wrapper` | 기존 LangGraph StateGraph 래핑 |

**functions (built-in 툴)**
| `_type` | 패키지 | 설명 |
|---------|--------|------|
| `current_datetime` | core | 현재 날짜/시간 |
| `chat_completion` | core | LLM 직접 호출 |
| `code_execution` | core | 코드 실행 |
| `wiki_search` | langchain | Wikipedia 검색 |
| `tavily_internet_search` | langchain | 웹 검색 |
| `webpage_query` | langchain | 특정 URL 내용 추출 |
| `github` | langchain | GitHub Issues/PRs 조회 |
| `mcp_client` | core | MCP 서버 툴 그룹 |

---

## 에이전트 실행 방법

```bash
# CLI 단발 실행
nat run --config_file config.yml

# HTTP 서버로 노출
nat serve --config_file config.yml --port 8080

# MCP 서버로 노출
nat mcp --config_file config.yml --port 9000

# A2A 서버로 노출 (본 프로젝트 표준)
nat a2a serve --config_file config.yml --port 8080
```

---

## A2A (Agent-to-Agent) 프로토콜

### 개요

A2A는 에이전트가 다른 에이전트에게 태스크를 위임할 수 있는 HTTP 기반 프로토콜이다.
본 프로젝트의 모든 에이전트는 A2A 서버로 배포하며, 에이전트 간 통신은 이 프로토콜을 통해 이루어진다.

### Agent Card

각 A2A 서버는 `/.well-known/agent.json` 경로에서 자신을 소개하는 Agent Card를 노출한다.

```json
{
  "name": "정보 수집 에이전트",
  "description": "Reddit, GitHub, HuggingFace 등에서 AI 제품 관련 정보를 수집한다.",
  "version": "0.1.0",
  "skills": [
    {
      "id": "collect_reddit",
      "name": "Reddit 수집",
      "description": "특정 AI 제품에 대한 Reddit 스레드와 댓글을 수집한다."
    }
  ]
}
```

### A2A 통신 흐름

```
[오케스트레이터 에이전트]
        │
        │  POST /tasks  (태스크 위임)
        ▼
[수집 에이전트 A2A 서버]
        │
        │  GET /.well-known/agent.json  (Agent Card 조회)
        │  POST /tasks/send
        ▼
[평가/필터링 에이전트 A2A 서버]
```

### 태스크 요청 형식

```json
{
  "id": "task-uuid",
  "message": {
    "role": "user",
    "parts": [
      { "text": "GPT-5에 대한 Reddit 반응을 수집해줘." }
    ]
  }
}
```

### 태스크 응답 형식

```json
{
  "id": "task-uuid",
  "status": { "state": "completed" },
  "artifacts": [
    {
      "parts": [
        { "text": "수집 결과 요약..." }
      ]
    }
  ]
}
```

---

## 커스텀 툴 등록

내장 툴로 커버되지 않는 기능(Reddit API, HuggingFace API 등)은 커스텀 함수로 등록한다.

```python
from nvidia_nat import register_function_group, FunctionGroup
from pydantic import BaseModel
from collections.abc import AsyncGenerator

class RedditSearchConfig(BaseModel):
    _type: str = "reddit_search"
    subreddit: str = "MachineLearning"

@register_function_group(config_type=RedditSearchConfig)
async def reddit_search_group(config: RedditSearchConfig) -> AsyncGenerator[FunctionGroup, None]:
    group = FunctionGroup(config=config)

    async def _search(query: str) -> str:
        """특정 서브레딧에서 쿼리에 해당하는 게시글을 검색한다."""
        ...
        return result

    group.add_function(name="reddit_search", fn=_search)
    yield group
```

`pyproject.toml`에 진입점 등록:

```toml
[project.entry-points."nat.components"]
reddit_search = "mypackage.tools.reddit:reddit_search_group"
```

config.yml에서 사용:

```yaml
functions:
  reddit:
    _type: reddit_search
    subreddit: MachineLearning
```

---

## 메모리 에이전트 (세션 간 컨텍스트 유지)

```yaml
workflow:
  _type: auto_memory_agent
  llm_name: primary_llm
  tool_names:
    - wiki_search
  memory:
    _type: mem0_memory
  verbose: true
```

`auto_memory_agent`는 내부적으로 `react_agent`를 래핑하며,
`user_id` 기준으로 대화 이력을 의미 검색(semantic search)으로 불러온다.

---

## MCP (Model Context Protocol) 연동

### NAT를 MCP 서버로 노출

```bash
nat mcp --config_file config.yml --port 9000
```

### 다른 에이전트의 config.yml에서 MCP 클라이언트로 연결

```yaml
functions:
  upstream_agent_tools:
    _type: mcp_client
    server:
      transport: streamable-http
      url: http://upstream-agent:9000
```

---

## 에이전트별 config.yml 위치 규칙

```
agents/
  collector/
    config.yml       # 정보 수집 에이전트
  evaluator/
    config.yml       # 평가/필터링 에이전트
  orchestrator/
    config.yml       # 오케스트레이터 에이전트
```

각 `config.yml`은 해당 에이전트의 단일 진실 공급원(single source of truth)이다.
배포 스크립트, 테스트, 문서는 모두 이 파일을 기준으로 동작해야 한다.

---

## 참고 링크

- 공식 개발자 자료: https://nemotron-dev-materials-q9notf2ox.brevlab.com/#tab=nat
- Nemotron-3 Nano 모델카드: https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard
- Nemotron-3 Super 모델카드: https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard
