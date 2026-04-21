---
name: get_benchmarks
description: LLM Benchmark API에서 모델 벤치마크 점수를 조회한다. provider·model·benchmark 이름으로 필터링 가능.
version: 0.1.0
tags: [benchmark, llm, evaluation, score]
parameters:
  provider:
    type: string
    description: "제공사 이름 부분 일치 필터 (예: OpenAI, Anthropic, Google)"
    required: false
  model:
    type: string
    description: "모델명 부분 일치 검색 (예: GPT-4o, Claude, Gemini)"
    required: false
  benchmark:
    type: string
    description: "벤치마크명 부분 일치 필터 (예: MMLU, GPQA, HumanEval)"
    required: false
---

# get_benchmarks

LLM Benchmark API(`BENCHMARK_API_URL`, 기본 `http://localhost:8000`)에서
벤치마크 점수 데이터를 조회한다.

리턴값: `{total, showing, results: ModelBenchmark[]}` JSON.

세 파라미터 모두 선택이며, 모두 생략하면 전체 목록을 반환한다.
