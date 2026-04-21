# AI Release Intelligence Agent

NVIDIA Nemotron Developer Days Seoul 2026 · Track A Creative Agentic Systems 출품작.

**"새 AI 모델·제품 발표가 뜨면, 공식 주장과 실사용자 반응을 자동 수집·대조·요약해서 10초 안에 핵심이 드러나는 한국어 리포트를 만드는 에이전트."**

2-agent 구성, NemoClaw(OpenClaw + NVIDIA OpenShell) 기반.

## 아키텍처

```
사용자 입력 (모델명·URL)
        ↓
┌───────────────────────────────────┐
│ Extractor Agent                   │ nemotron-3-nano-30b-a3b
│ blueprint: extractor/blueprint.yaml│
│ skills:                           │
│  ─ scrape_rss          (15 feeds) │
│  ─ scrape_arxiv                   │
│  ─ scrape_reddit       (.json)    │
│  ─ scrape_hackernews              │
│  ─ scrape_github                  │
│  ─ scrape_hf_papers               │
│  ─ enrich_bodies  (trafilatura)   │
└───────────────────────────────────┘
        ↓ EvidenceItem[] JSON
┌───────────────────────────────────┐
│ Validator Agent                   │ nemotron-3-super-120b-a12b
│ blueprint: validator/blueprint.yaml│
│ skills:                           │
│  ─ extract_claims  (LLM-backed)   │
│  ─ validate_sources (rule-based)  │
│  ─ synthesize_report (LLM-backed) │
└───────────────────────────────────┘
        ↓
한국어 cited 마크다운 리포트
(TL;DR / 매트릭스 / Quote / 대립구도 / 회의론 / Final)
```

## 구현 개요

- **에이전트 런타임:** OpenClaw (JavaScript ESM skills). NemoClaw 샌드박스로 승격 가능(Linux 5.13+ 필요).
- **비즈니스 로직:** Python 3.12 (`ari_agent/` 패키지).
  - Scrapers 6종 + body enricher(trafilatura) + rule-based source validator가 모두 **framework-agnostic**.
  - 각 skill은 `python -m ari_agent.cli <subcommand>`를 subprocess로 호출.
- **LLM:** Nemotron-3-Super(synthesis) + Nemotron-3-Nano(claim 추출). Provider는 env 스위치로 3경로 지원 (Brev vLLM / NVIDIA Build API / self-host NIM).

## Quickstart

### 1. 로컬 (Mac) — 개발·검증

```bash
# 의존성 (venv 권장)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# Python CLI 단독 검증
python -m ari_agent.cli health
python -m ari_agent.cli scrape_rss --feed-key simon_willison --limit 3
python -m ari_agent.cli scrape_arxiv --query "nemotron" --limit 5

# stdin 파이프
python -m ari_agent.cli scrape_rss --feed-key simon_willison --limit 5 \
  | python -m ari_agent.cli validate_sources

# Node로 skill 직접 호출 (OpenClaw 없어도 됨)
ARI_AGENT_HOME=$(pwd) node --input-type=module -e "
  import mod from './extractor/skills/scrape_rss/index.mjs';
  console.log(JSON.stringify(await mod.execute({feed_key:'simon_willison', limit:3}), null, 2));
"
```

### 2. Brev 인스턴스 — 데모

```bash
# OpenClaw가 이미 설치된 Brev 샌드박스에서
git clone <this-repo>
cd nvidia-nemotron-hackathon-2026
git checkout feat/openclaw-migration
pip install -e .

# LLM provider 확인
openshell inference get

# Extractor 호출
openclaw agent --agent extractor --local \
  -m "Claude Opus 4.7 evidence를 arxiv/reddit/github에서 각 5건씩 수집해줘" \
  --session-id demo-001

# Validator 호출
openclaw agent --agent validator --local \
  -m "위 evidence + 공식 URL(https://www.anthropic.com/news/claude-opus-4-7)으로 한국어 리포트 생성"
```

### 3. LLM provider 스위치 (4경로)

```bash
# (A) 팀원 Brev endpoint — 기본, 무인증. Super/Nano 각각 별도 엔드포인트.
export ARI_LLM_PROVIDER=brev
# 자동 라우팅:
#   tier=super → https://model-server-uya78rbya.brevlab.com/v1
#   tier=nano  → https://model-server-4dfr8gv78.brevlab.com/v1 (모델 id: nvidia/nemotron-3-nano)

# (B) NVIDIA Build API — nvapi- 키 필요, GPU 불필요
export ARI_LLM_PROVIDER=build
export NVIDIA_API_KEY=nvapi-...

# (C) Self-host NIM on Brev H100 — 가장 강한 NeMo 스택 어필
docker run --gpus all --shm-size=16g -e NGC_API_KEY=$NGC_API_KEY \
  -v ~/.cache/nim:/opt/nim/.cache -p 8000:8000 \
  nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:latest
export ARI_LLM_PROVIDER=local-nim

# (D) Friendli 대체 LLM (Nemotron 미호스팅, 백업·비교용)
export ARI_LLM_PROVIDER=friendli
export FRIENDLI_API_KEY=...  FRIENDLI_TEAM_ID=...
# 기본 매핑: Super=Qwen3-235B-A22B-Instruct-2507, Nano=llama-3.3-70b-instruct
```

## 디렉토리

```
.
├── AGENTS.md / SOUL.md / IDENTITY.md / USER.md / TOOLS.md   OpenClaw workspace 페르소나
├── ari_agent/              Python 패키지 (scrapers, enrichers, validators, cli, llm_client)
├── _lib/ari_cli.mjs        skills가 공유하는 Python subprocess 헬퍼
├── extractor/              수집 에이전트 (blueprint + 7 skills)
├── validator/              검증·종합 에이전트 (blueprint + 3 skills)
├── tests/                  pytest (scrapers 17/17, enricher, validator 8/8)
├── tools/summarize_targets.py  백업 데모 경로 (NAT/OpenClaw 없이 독립 실행)
├── docs/                   가이드 3종 + 향후 리포트 산출물
└── pyproject.toml
```

## 심사 포인트

- **NeMo 스택 깊이:** Nemotron-3 Nano + Super 이종 모델 분업, OpenClaw/NemoClaw 런타임, (옵션) self-host NIM 3종 동시 지원.
- **Agentic 패턴:** 2-agent 분업 + 각 에이전트의 ReAct-style skill 선택. 단순 파이프라인이 아니라 LLM 주도 orchestration.
- **실사용 증거:** 공식 주장과 Reddit/GitHub Issues/Gary Marcus 등 비판 소스를 **구조적으로** 수집해 대립 구도를 자동 생성.
- **한국어 UX:** 심사관·개발자가 10초에 핵심 파악. 영어 원문 인용 + 한국어 요지 병기.
