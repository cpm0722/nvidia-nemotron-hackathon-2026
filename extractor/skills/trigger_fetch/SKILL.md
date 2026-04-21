---
name: trigger_fetch
description: LLM Benchmark API에 최신 벤치마크 데이터 수집을 즉시 요청한다. RSS·Anthropic·HuggingFace·Artificial Analysis 모든 소스 대상.
version: 0.1.0
tags: [benchmark, fetch, update, crawl]
parameters: {}
---

# trigger_fetch

LLM Benchmark API 서버에 `POST /fetch`를 호출해 모든 소스에서 최신 벤치마크 데이터를
백그라운드 수집하도록 요청한다.

수집은 서버 백그라운드에서 비동기로 진행되며, 실제 완료까지 수 분이 걸릴 수 있다.
결과 확인은 `get_status` skill로 한다.

리턴값: `{message: string}` JSON.
