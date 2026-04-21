---
name: scrape_rss
description: RSS/Atom 피드에서 최근 게시물을 수집한다. 사전 등록된 키(openai/deepmind/anthropic/simon_willison/gary_marcus/geeknews 등) 또는 임의 URL 지원.
version: 0.1.0
tags: [scraping, rss, evidence-collection]
parameters:
  feed_key:
    type: string
    description: "등록된 피드 키. feed_url과 배타. 예: simon_willison, gary_marcus, geeknews"
    required: false
  feed_url:
    type: string
    description: "임의 RSS/Atom URL. feed_key와 배타."
    required: false
  query:
    type: string
    description: "제목+본문 부분 일치 필터(대소문자 무관). 비워두면 최근 게시물 전체."
    required: false
  limit:
    type: integer
    description: "최대 항목 수(1~100). 기본 20."
    required: false
---

# scrape_rss

AI 블로그·뉴스레터 RSS 피드에서 최근 게시물을 수집한다.
리턴값은 `{evidence: EvidenceItem[], stats: {...}}` 형태의 JSON.

Evidence는 `body_full`이 아직 비어 있으므로, 필요 시 뒤이어 `enrich_bodies`로 본문 보강을 할 것.
