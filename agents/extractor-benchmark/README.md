# extractor-benchmark

NAT A2A 에이전트 — LLM 모델명 하나로 **Artificial Analysis**와 **HuggingFace**에서 벤치마크 점수와 최신 사용자 토론을 수집해 통합 JSON으로 반환한다.

## 노출 툴

**`search_benchmarks(model_name: str)`** — 단일 툴
- AA 전체 모델 목록에서 벤치마크 점수 조회
- HF 모델 카드에서 벤치마크 점수 조회
- HF 모델 페이지에서 최신 토론 본문·댓글 조회
- 두 소스 합산 (AA 우선, 중복 벤치마크명 제거)

## 실행

### 1) A2A 서버 기동 (포트 10001)

```bash
bash scripts/a2a_server.sh
```

### 2) A2A 클라이언트로 호출

```bash
bash scripts/a2a_client.sh "claude opus 4.7"
bash scripts/a2a_client.sh "gemma 3"
bash scripts/a2a_client.sh "gpt-5"
```

### 3) 로컬 직접 실행 (A2A 없이)

```bash
bash scripts/run.sh "claude opus 4.7"
```

## 반환 포맷 (BenchmarkResult)

```json
{
  "model_name": "Claude Opus 4.7",
  "provider": "Anthropic",
  "benchmarks": [
    {"name": "Intelligence Index", "score": 85.2, "score_str": "85.2", "source": "Artificial Analysis"},
    {"name": "MMLU", "score": 89.1, "score_str": "89.1%", "source": "HuggingFace"}
  ],
  "sources": ["Artificial Analysis", "HuggingFace"],
  "hf_discussions": [
    {
      "title": "...",
      "num": 12,
      "author": "...",
      "created_at": "...",
      "status": "open",
      "num_comments": 5,
      "url": "https://huggingface.co/.../discussions/12",
      "body": "...",
      "comments": [{"author": "...", "text": "...", "created_at": "..."}]
    }
  ],
  "hf_model_card": "# Model Card\n\n...<원본 README.md 전문>..."
}
```

## 구조

```
extractor-benchmark/
├── configs/config.yml           # NAT 워크플로우 설정 (A2A, LLM, function group)
├── prompts/system_prompt.txt    # ReAct 에이전트용 시스템 프롬프트
├── scripts/                     # run / a2a_server / a2a_client
├── pyproject.toml               # nvidia-nat[a2a,langchain] 의존성
└── src/nat_extractor_benchmark/
    ├── register.py              # @register_function_group → search_benchmarks 툴
    ├── orchestrator.py          # AA + HF 합산 로직
    ├── models.py                # Pydantic: BenchmarkItem / HFDiscussion / BenchmarkResult
    └── scrapers/
        ├── artificialanalysis.py  # fetch_model_benchmarks
        └── huggingface.py         # fetch_benchmarks_for_model, fetch_discussions
```
