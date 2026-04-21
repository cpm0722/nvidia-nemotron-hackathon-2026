# extractor-benchmark

NAT A2A 에이전트 — LLM 모델명 하나로 **Artificial Analysis**와 **HuggingFace**에서 벤치마크 점수·사용자 토론·모델 카드 원문을 수집한다. 모든 결과는 [`ari_core`](../../libs/ari-core/)의 `EvidenceItem` 스키마로 정규화되어 반환된다.

## 노출 툴

**`search_benchmarks(model_name: str)`** — 단일 툴
- Artificial Analysis 전체 모델 목록에서 벤치마크 점수 조회
- HuggingFace 모델 카드에서 벤치마크 점수 + README.md 원문 조회
- HuggingFace 모델 페이지에서 최신 토론 본문·댓글 조회
- 결과를 `ari_core.EvidenceItem`으로 정규화 → 단일 `ScrapeResult`로 반환

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

## 반환 포맷 (`ari_core.ScrapeResult`)

```json
{
  "source": "benchmark",
  "ok": true,
  "latency_ms": 3421,
  "fetched_at": "2026-04-21T10:00:00Z",
  "items": [
    {
      "source": "artificial_analysis",
      "source_detail": "artificialanalysis.ai",
      "url": "https://artificialanalysis.ai/models/claude-opus-4-7",
      "title": "Claude Opus 4.7",
      "text": "Claude Opus 4.7 benchmarks from Artificial Analysis: Intelligence Index=85.2, MMLU-Pro=89.1%, ...",
      "metadata": {
        "kind": "benchmark_scores",
        "provider": "Anthropic",
        "model_name": "Claude Opus 4.7",
        "slug": "claude-opus-4-7",
        "benchmarks": [
          {"name": "Intelligence Index", "score": 85.2, "score_str": "85.2"}
        ]
      }
    },
    {
      "source": "huggingface",
      "source_detail": "huggingface.co/anthropic/claude-opus-4-7",
      "url": "https://huggingface.co/anthropic/claude-opus-4-7",
      "title": "claude-opus-4-7",
      "text": "claude-opus-4-7 benchmarks from HuggingFace model card: MMLU=89.1%, ...",
      "body_full": "# Model Card\n\n...<README.md 원문 전체>...",
      "metadata": {
        "kind": "benchmark_scores",
        "provider": "anthropic",
        "model_id": "anthropic/claude-opus-4-7",
        "benchmarks": [{"name": "MMLU", "score": 89.1, "score_str": "89.1%"}]
      }
    },
    {
      "source": "huggingface",
      "source_detail": "huggingface.co/anthropic/claude-opus-4-7/discussions",
      "url": "https://huggingface.co/anthropic/claude-opus-4-7/discussions/12",
      "title": "Question about context length",
      "author": "user123",
      "text": "...discussion body...",
      "timestamp": "2026-04-10T12:34:00Z",
      "score": 5,
      "metadata": {
        "kind": "discussion",
        "model_id": "anthropic/claude-opus-4-7",
        "discussion_num": 12,
        "status": "open",
        "comments": [{"author": "...", "text": "...", "created_at": "..."}]
      }
    }
  ]
}
```

### EvidenceItem 종류

| `source` / `metadata.kind` | 건수 | 핵심 필드 |
|---|---|---|
| `artificial_analysis` / `benchmark_scores` | 0 or 1 | `metadata.benchmarks` (원시 점수 리스트) |
| `huggingface` / `benchmark_scores` | 0 or 1 | `metadata.benchmarks`, `body_full` (모델 카드 원문) |
| `huggingface` / `discussion` | 0 ~ N | `text` (본문), `metadata.comments` (댓글) |

총 item 수는 `config.default_limit`을 넘지 않음. AA + HF 벤치 이후 남은 슬롯이 HF 토론으로 채워진다.

## 구조

```
extractor-benchmark/
├── configs/config.yml           # NAT 워크플로우 설정 (A2A, LLM, function group)
├── prompts/system_prompt.txt    # ReAct 에이전트용 시스템 프롬프트
├── scripts/                     # run / a2a_server / a2a_client
├── pyproject.toml               # nvidia-nat + ari_core + httpx + bs4 + lxml
└── src/nat_extractor_benchmark/
    ├── register.py              # @register_function_group → search_benchmarks 툴
    ├── scraper.py               # ari_core 어댑터 (EvidenceItem 정규화)
    └── scrapers/
        ├── artificialanalysis.py  # fetch_model_benchmarks (RSC flight 파싱)
        └── huggingface.py         # fetch_benchmarks_for_model + fetch_discussions
```
