---
name: scrape_arxiv
description: arXiv에서 query에 매칭되는 최근 논문을 수집한다. export.arxiv.org API(1 req / 3 sec throttle 준수).
version: 0.1.0
tags: [scraping, arxiv, papers, evidence-collection]
parameters:
  query:
    type: string
    description: "검색어 (예: 'nemotron', 'claude opus tool-use')"
    required: true
  limit:
    type: integer
    description: "최대 논문 수. 기본 20."
    required: false
  since_days:
    type: integer
    description: "최근 N일 이내 게시물만(기본 30)."
    required: false
---

# scrape_arxiv

arXiv에서 query 관련 최근 논문을 수집한다. 리턴값은 `{evidence, stats}` JSON.
