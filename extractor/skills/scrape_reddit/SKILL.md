---
name: scrape_reddit
description: 지정된 서브레딧에서 query에 매칭되는 최근 스레드를 수집한다. OAuth 없이 .json fallback 사용(2025-11 차단 이후 검증됨).
version: 0.1.0
tags: [scraping, reddit, community-signal]
parameters:
  query:
    type: string
    description: "검색어"
    required: true
  subreddits:
    type: string
    description: "콤마 구분 목록(예: 'LocalLLaMA,MachineLearning'). 비우면 기본 프리셋."
    required: false
  limit:
    type: integer
    description: "최대 스레드 수. 기본 20."
    required: false
  since_days:
    type: integer
    description: "최근 N일. 기본 30."
    required: false
---

# scrape_reddit

Reddit `.json` 공개 엔드포인트로 서브레딧 스레드를 수집한다. OAuth 미사용.
