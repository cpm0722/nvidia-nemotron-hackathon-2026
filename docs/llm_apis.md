# LLM APIs

## 1. Onpremise API (NVIDIA Nemotron-3)

Brev(NVIDIA computing resource)에서 GPU instance를 직접 할당받아 배포한 OpenAI-compatible API (NIM + vLLM).

- **API Key**: 불필요 (`"empty"` 사용)
- **호환 방식**: OpenAI API (`/v1/chat/completions` 등)

| Model | Base URL |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | `https://model-server-uya78rbya.brevlab.com/v1` |
| `nvidia/nemotron-3-nano-30b-a3b` | `https://model-server-4dfr8gv78.brevlab.com/v1` |

**사용 예시:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://model-server-uya78rbya.brevlab.com/v1",
    api_key="empty",
)
```

---

## 2. Friendli API

Friendli Serverless Inference의 OpenAI-compatible API.

- **Base URL**: `https://api.friendli.ai/serverless/v1`
- **인증**: `.env`에서 `FRIENDLI_API_KEY`, `FRIENDLI_TEAM_ID` 로드
  - `Authorization: Bearer $FRIENDLI_API_KEY`
  - `X-Friendli-Team: $FRIENDLI_TEAM_ID`

**사용 예시:**
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.friendli.ai/serverless/v1",
    api_key=os.environ["FRIENDLI_API_KEY"],
    default_headers={"X-Friendli-Team": os.environ["FRIENDLI_TEAM_ID"]},
)
```

### 사용 가능한 모델

| Model ID | Context | Max Output | Tool Call | 가격 (input/output, $/M tok) |
|---|---|---|---|---|
| `meta-llama-3.3-70b-instruct` | 131,072 | 131,072 | ✅ | $0.6 / $0.6 |
| `meta-llama-3.1-8b-instruct` | 131,072 | 8,000 | ✅ | $0.1 / $0.1 |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | 262,144 | 262,144 | ✅ | $0.2 / $0.8 |
| `LGAI-EXAONE/K-EXAONE-236B-A23B` | 262,144 | 262,144 | ✅ | $0.2 / $0.8 |
| `zai-org/GLM-5` | 202,752 | 202,752 | ✅ | $1.0 / $3.2 |
| `zai-org/GLM-5.1` | 202,752 | 202,752 | ✅ | $1.4 / $4.4 |
| `MiniMaxAI/MiniMax-M2.5` | 196,608 | 196,608 | ✅ | $0.3 / $1.2 |
| `deepseek-ai/DeepSeek-V3.2` | 163,840 | 163,840 | ✅ | $0.5 / $1.5 |

> 모델 목록은 `GET https://api.friendli.ai/serverless/v1/models` 로 최신 목록 확인 가능.
