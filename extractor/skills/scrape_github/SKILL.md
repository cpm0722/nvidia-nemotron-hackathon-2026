---
name: scrape_github
description: GitHub 이슈·PR·릴리스에서 query 매칭 항목을 수집한다. GITHUB_TOKEN env로 rate-limit을 5000/hr까지 끌어올릴 수 있다.
version: 0.1.0
tags: [scraping, github, issues, release-engineering]
parameters:
  query:
    type: string
    description: "검색어"
    required: true
  repo:
    type: string
    description: "특정 레포 고정(예: 'anthropics/anthropic-sdk-python')."
    required: false
  limit:
    type: integer
    description: "최대 항목 수. 기본 20."
    required: false
  since_days:
    type: integer
    description: "최근 N일. 기본 30."
    required: false
---

# scrape_github

GitHub Issues/PR/Releases 검색. SDK/프레임워크 쪽 실사용 이슈 수집에 유용.
