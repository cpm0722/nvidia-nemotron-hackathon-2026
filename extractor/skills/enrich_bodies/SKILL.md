---
name: enrich_bodies
description: scrape_* skill들이 반환한 evidence의 `body_full` 필드를 trafilatura로 채운다. 입력/출력 모두 `{evidence:[...]}` 형태.
version: 0.1.0
tags: [enrichment, trafilatura, evidence-processing]
parameters:
  evidence:
    type: array
    description: "scrape_*의 evidence 배열(개별 항목은 EvidenceItem 스키마). JSON 인자 또는 stdin."
    required: true
  workers:
    type: integer
    description: "동시 작업 스레드 수. 기본 5."
    required: false
---

# enrich_bodies

EvidenceItem 배열을 받아 URL별 본문을 `trafilatura`로 추출·삽입한다.
Reddit/X/YouTube 등 skip 대상 도메인은 `body_full`을 그대로 null로 둔다.
