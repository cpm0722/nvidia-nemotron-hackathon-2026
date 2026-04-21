---
name: scrape_hf_papers
description: HuggingFace Papers에서 query 매칭 논문·모델 카드를 수집한다.
version: 0.1.0
tags: [scraping, huggingface, papers, evidence-collection]
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

# scrape_hf_papers

HuggingFace Papers(`huggingface.co/papers`) 검색. arXiv 링크·커뮤니티 투표 포함.
