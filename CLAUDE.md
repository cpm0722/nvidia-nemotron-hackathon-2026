### TL;DR
- 2026 엔비디아 Nemotron Hackathon의 Track A "Creative Agentic Systems" 프로젝트
- 새로 나온 AI 프러덕트 (모델, API, 솔루션, 프레임워크, Feature 등)에 대한 오피셜한 성능(벤치마크 등)과 실사용자 반응 및 피드백을 모아서 요약/정리하는 에이전트
- Agent Framework: NemoClaw(OpenClaw + NVIDIA의 보안 솔루션) 기반
- Backbone Model: [Nemotron-3-Nano-30B-A3B](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b/modelcard), [Nemotron-3-Super-120B-A12B](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
- GPU Resource: H100 4GPU


### Architecture
- Extractor: 다양한 출처에서 정보를 수집하는 Agent
  - 정보 출처
    - Official Blog
    - Benchmark site
    - arxiv.org (paper)
    - Reddit
    - GitHub Issue
    - HuggingFace

- Validator: 수집한 정보를 검증/필터링하는 Agent

---

### Current Implementation (2026-04-21, branch `feat/openclaw-migration`)

OpenClaw workspace + Python 비즈니스 로직 하이브리드:

| 레이어 | 경로 | 역할 |
|---|---|---|
| Agent | `extractor/blueprint.yaml`, `validator/blueprint.yaml` | OpenClaw 에이전트 2개 (skill 7 + 3) |
| Skill | `extractor/skills/*/`, `validator/skills/*/` | JS ESM, `_lib/ari_cli.mjs`로 Python subprocess 호출 |
| CLI | `ari_agent/cli.py` (argparse, 10 subcommands) | 모든 skill이 공통 진입점으로 사용 |
| LLM | `ari_agent/llm_client.py` (3-provider 스위치) | brev (default) / build / local-nim |
| Scrapers/Enricher/Validator | `ari_agent/scrapers|enrichers|validators/` | framework-agnostic 순수 Python |

**핵심 명령어:**
```bash
python -m ari_agent.cli health                     # provider 확인
python -m ari_agent.cli scrape_rss --feed-key simon_willison --limit 3
openclaw agent --agent extractor --local -m "..."  # Brev에서
```

**관련 문서:**
- `README.md` — 전체 구동 가이드
- `TOOLS.md` — 실행 환경·provider 스위치·서브커맨드 참조
- `SOUL.md` — 분석 에이전트 페르소나/금지선
- `docs/` — NemoClaw / NAT / NIM 배포 공식 가이드

### 세션 진입 시

1. 새 요청이 들어오면 `README.md` 또는 `TOOLS.md` 먼저 확인 (런타임 상태 파악).
2. "다음 할 일" 질문이면 부모 디렉토리 `../NEXT_TASKS.md` 참조.
3. skill 추가/수정 시 반드시 `ari_agent/cli.py`의 서브커맨드 매핑도 동기화.
