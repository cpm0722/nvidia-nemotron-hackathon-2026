---
name: scrape_reddit
description: 지정된 서브레딧에서 query에 매칭되는 최근 스레드를 수집한다. OAuth 없이 .json fallback 사용(2025-11 차단 이후 검증됨). 클라우드 IP(Brev 등)가 Reddit에 403 당하면 cache_file로 사전 수집 스냅샷 로드.
version: 0.2.0
tags: [scraping, reddit, community-signal]
parameters:
  query:
    type: string
    description: "검색어 (cache_file 사용 시 생략 가능)"
    required: false
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
  cache_file:
    type: string
    description: "사전 수집 JSON 스냅샷 경로(예: docs/cache/reddit-claude-opus-4.7.json). 설정 시 HTTP 호출을 건너뛰고 파일에서 로드. Brev 등 클라우드 IP에서 Reddit이 403을 리턴할 때 사용."
    required: false
---

# scrape_reddit

Reddit `.json` 공개 엔드포인트로 서브레딧 스레드를 수집한다. OAuth 미사용.

## 클라우드 IP 환경(Brev, AWS 등)에서 사용

Reddit은 주요 클라우드 IP 레인지를 HTTP 403으로 차단한다. 이 때:

1. **로컬(레지던셜 IP)에서** 먼저 스냅샷 수집 — `docs/cache/reddit-{target}.json`으로 커밋해 둔다.
2. **데모 환경(Brev)에서는** `cache_file: docs/cache/reddit-claude-opus-4.7.json` 식으로 로드.

스냅샷 생성 예 (로컬 Mac):
```bash
python -m ari_agent.cli scrape_reddit \
  --query "Claude Opus 4.7" \
  --subreddits "LocalLLaMA,MachineLearning,ClaudeAI" \
  --limit 20 \
  > docs/cache/reddit-claude-opus-4.7.json
```

## 실패 시 반응

cache_file도 없고 HTTP도 403이면 `stats.error` 필드에 "r/<sub>: HTTP 403" 명시. 에이전트가 사용자에게 투명하게 보고해야 함 (숨기지 말 것).
