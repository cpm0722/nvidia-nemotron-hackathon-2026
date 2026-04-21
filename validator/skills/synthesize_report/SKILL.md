---
name: synthesize_report
description: claims + evidence + (선택) model_name을 받아 한국어 cited 마크다운 리포트를 생성한다. Nemotron-3-Super 사용, 응답 시간 15~25초.
version: 0.1.0
tags: [llm, synthesis, korean-report]
parameters:
  claims:
    type: array
    description: "{id, text, ...} 배열 또는 extract_claims 결과 객체"
    required: true
  evidence:
    type: array
    description: "EvidenceItem 배열 (enrich/validate 후 권장)"
    required: true
  model_name:
    type: string
    description: "분석 대상 모델 표시명 (예: Claude Opus 4.7)"
    required: false
  top_n:
    type: integer
    description: "Validator 점수 상위 N건만 프롬프트로 전달(기본 40)."
    required: false
  max_tokens:
    type: integer
    description: "Nemotron 응답 max_tokens. 기본 6000."
    required: false
---

# synthesize_report

최종 산출물: 한국어 마크다운 리포트 (TL;DR / Claim↔Evidence 매트릭스 / 핵심 Quote / 대립 구도 / 회의론 신호 / Final Assessment).
- Nemotron-3-Super (`ARI_NEMOTRON_SUPER`) 기본 사용
- Thinking mode 비활성 (`enable_thinking=false`), 15~25초 응답
