# Nemotron-3-Super NIM 배포 가이드 (H100 2GPU, FP8)

NIM(NVIDIA Inference Microservice) 컨테이너를 사용해 Nemotron-3-Super-120B-A12B를
H100 2장에서 FP8로 서빙하고 OpenAI 호환 API로 호출하는 방법을 설명합니다.

## 모델 사양

| 항목 | 내용 |
|------|------|
| 모델 | Nemotron-3-Super-120B-A12B |
| 총 파라미터 | 120B (MoE: 토큰당 12B 활성) |
| 아키텍처 | LatentMoE + Mamba-2 Hybrid + MTP |
| 최대 컨텍스트 | 1M tokens |
| 권장 정밀도 (H100) | FP8 |

## 전제 조건

- H100 GPU × 2 (각 80GB, 총 160GB)
- Docker 설치
- NGC API Key ([NGC 발급 링크](https://org.ngc.nvidia.com/setup/api-key))
- 디스크 여유 공간 약 130GB 이상 (모델 캐시)

---

## 1단계: NGC 인증

```bash
# NGC API Key 환경변수 설정
export NGC_API_KEY=<your-ngc-api-key>

# Docker 레지스트리 로그인
docker login nvcr.io -u '$oauthtoken' -p $NGC_API_KEY
```

---

## 2단계: 모델 캐시 디렉터리 생성

NIM 컨테이너는 최초 실행 시 모델 가중치를 자동으로 다운로드합니다.
이후 실행에서는 캐시를 재사용하므로 로컬 경로를 마운트해 둡니다.

```bash
mkdir -p ~/.cache/nim
```

---

## 3단계: NIM 컨테이너 실행

```bash
docker run -it --rm \
  --gpus all \
  --shm-size=16g \
  -e NGC_API_KEY=$NGC_API_KEY \
  -v ~/.cache/nim:/opt/nim/.cache \
  -p 8000:8000 \
  nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:latest
```

### 플래그 설명

| 플래그 | 설명 |
|--------|------|
| `--gpus all` | H100 2장 전부 할당 (NIM이 GPU 수 자동 감지 후 TP 설정) |
| `--shm-size=16g` | 멀티 GPU 간 NCCL 통신용 공유 메모리 |
| `-e NGC_API_KEY` | 모델 가중치 다운로드 인증 |
| `-v ~/.cache/nim:/opt/nim/.cache` | 모델 캐시 영속화 (재실행 시 재다운로드 방지) |
| `-p 8000:8000` | OpenAI 호환 API 포트 노출 |

> **참고:** NIM 컨테이너는 H100을 감지하면 자동으로 FP8 최적화 엔진을 선택합니다.
> 최초 실행 시 TRT-LLM 엔진 빌드가 수행되므로 서버 준비까지 수 분이 소요됩니다.

---

## 4단계: API 호출

서버 로그에 `Server ready` 메시지가 출력되면 아래와 같이 호출합니다.

### 서버 상태 확인

```bash
curl http://localhost:8000/v1/models
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-3-super-120b-a12b",
    "messages": [
      {"role": "user", "content": "Explain the difference between MoE and dense transformers."}
    ],
    "max_tokens": 512,
    "temperature": 0.6
  }'
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="no-key",  # self-hosted NIM은 인증 불필요
)

response = client.chat.completions.create(
    model="nemotron-3-super-120b-a12b",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=256,
    temperature=0.6,
)
print(response.choices[0].message.content)
```

### Thinking Mode (추론 모드)

```python
response = client.chat.completions.create(
    model="nemotron-3-super-120b-a12b",
    messages=[{"role": "user", "content": "Solve: if 2x + 3 = 11, what is x?"}],
    max_tokens=1024,
    extra_body={"thinking": {"type": "enabled"}},
)
print(response.choices[0].message.content)
```

---

## 클라우드 API 사용 (GPU 없이 테스트)

GPU 환경 없이 빠르게 API를 테스트하려면 NVIDIA Build API를 사용합니다.

```bash
# build.nvidia.com에서 nvapi- 키 발급
export NVIDIA_API_KEY=nvapi-xxxx...
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="nvapi-xxxx...",
)

response = client.chat.completions.create(
    model="nvidia/nemotron-3-super-120b-a12b",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=256,
)
print(response.choices[0].message.content)
```

---

## 트러블슈팅

**컨테이너 pull 실패**
```bash
# NGC 로그인 재시도
docker login nvcr.io -u '$oauthtoken' -p $NGC_API_KEY
```

**OOM (메모리 부족)**
```bash
# shm-size 증량
--shm-size=32g

# 특정 GPU만 지정하여 다른 프로세스와 격리
--gpus '"device=0,1"'
```

**엔진 빌드 중 타임아웃**

최초 실행 시 TRT-LLM 엔진 빌드에 10~30분 소요될 수 있습니다.
`~/.cache/nim`에 빌드 결과가 캐시되므로 이후 실행은 수십 초 내에 완료됩니다.

**NCCL 통신 오류**
```bash
-e NCCL_P2P_DISABLE=0 \
-e NCCL_IB_DISABLE=0
```
