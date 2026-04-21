---
name: scrape_hackernews
description: Hacker News Algolia 검색으로 query에 매칭되는 최근 스토리와 주요 댓글을 수집한다.
version: 0.1.0
tags: [scraping, hackernews, community-signal]
parameters:
  query:
    type: string
    description: "검색어"
    required: true
  limit:
    type: integer
    description: "최대 항목 수. 기본 20."
    required: false
  since_days:
    type: integer
    description: "최근 N일. 기본 30."
    required: false
---

# scrape_hackernews

HN Algolia(`hn.algolia.com`) 기반 검색. 점수·댓글 수·작성자 포함.
