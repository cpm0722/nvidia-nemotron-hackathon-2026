---
name: validate_sources
description: EvidenceItem 배열을 받아 출처 권위성(authority)·검증가능성(verifiability)을 룰 기반 2축으로 점수화. 호출마다 LLM 사용하지 않음.
version: 0.1.0
tags: [validation, source-scoring, rule-based]
parameters:
  evidence:
    type: array
    description: "EvidenceItem 배열. stdin JSON으로 전달."
    required: true
---

# validate_sources

도메인 화이트리스트(arxiv 5.0, anthropic 5.0, reddit 2.5 등) + 링크 수/수치 언급 수(verifiability) + 작성자 신호(bot, anon, high-upvote)로 2축 점수를 매긴다.
산출: `{validations:[{url, authority, verifiability, aggregate, reasons:[...]}]}`.
