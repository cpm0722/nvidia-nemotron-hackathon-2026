---
name: extract_claims
description: 공식 release URL(모델 카드/블로그/페이퍼)을 받아 검증 가능한 claim 목록을 LLM(Nemotron Nano)으로 추출한다.
version: 0.1.0
tags: [llm, claim-extraction, validation]
parameters:
  url:
    type: string
    description: "공식 릴리스 URL (예: https://www.anthropic.com/news/claude-opus-4-7)"
    required: true
  max_input_chars:
    type: integer
    description: "페이지 본문에서 잘라낼 최대 문자수. 기본 8000."
    required: false
---

# extract_claims

입력: 공식 릴리스 URL.
출력: `{model_name, claims:[{id, text, kind, evidence_hints[]}]}` (JSON).
- `kind`: benchmark|capability|scale|cost|safety
- `evidence_hints`: 후속 scrape_* 호출에 쓸 2~4개 검색 키워드
