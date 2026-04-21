---
name: get_status
description: LLM Benchmark API의 소스별 마지막 수집 시각·결과·에러를 반환한다.
version: 0.1.0
tags: [benchmark, status, monitoring]
parameters: {}
---

# get_status

각 수집 소스(rss_openai, rss_deepmind, anthropic, huggingface, artificialanalysis 등)의
마지막 수집 시각(`last_fetched`), 새로 추가된 항목 수(`last_new_count`), 에러 메시지(`error`)를 반환한다.

리턴값: `{[source]: {last_fetched, last_new_count, error}}` JSON.
