# TOOLS.md — AI Release Intelligence Agent 운영 메모

Skills가 어떻게 동작하는지가 아니라, **이 워크스페이스의 구체적 실행 환경** 메모.

## Python 백엔드 (`ari_agent/`)

| 항목 | 값 |
|---|---|
| 패키지 | `ari_agent` (로컬 `pyproject.toml` 기반 editable install) |
| 진입점 | `python -m ari_agent.cli <subcommand>` |
| 서브커맨드 10개 | scrape_rss / scrape_arxiv / scrape_reddit / scrape_hackernews / scrape_github / scrape_hf_papers / enrich_bodies / extract_claims / validate_sources / synthesize_report (+ `health`) |
| 런타임 | Python 3.11~3.13 (3.14는 pydantic/feedparser 호환성 이슈 가능) |
| 설치 | `pip install -e .` (워크스페이스 루트에서) |

**환경변수 스위치 (`llm_client.py`):**
```bash
export ARI_LLM_PROVIDER=brev       # brev | build | local-nim | friendli
# 선택적 override
export NEMOTRON_SUPER_BASE_URL=https://model-server-uya78rbya.brevlab.com/v1
export NEMOTRON_NANO_BASE_URL=https://model-server-4dfr8gv78.brevlab.com/v1
export NVIDIA_API_KEY=nvapi-...              # build provider
export FRIENDLI_API_KEY=...  FRIENDLI_TEAM_ID=...   # friendli provider
```

## Nemotron / LLM 엔드포인트 4경로

| Provider | Super Base URL | Nano Base URL | 인증 | 참고 |
|---|---|---|---|---|
| `brev` (기본) | `https://model-server-uya78rbya.brevlab.com/v1` | `https://model-server-4dfr8gv78.brevlab.com/v1` | `api_key="empty"` | 팀원 호스팅 vLLM. **Nano 모델 id는 짧은 `nvidia/nemotron-3-nano`** (Super와 다름) |
| `build` | `https://integrate.api.nvidia.com/v1` | 동일 | `NVIDIA_API_KEY`(nvapi-) | GPU 불필요, rate limit |
| `local-nim` | `http://localhost:8000/v1` | 동일 | 없음 | Brev H100에서 NIM 컨테이너 운영 시, Super/Nano 각각 별도 포트 필요하면 `NEMOTRON_*_BASE_URL` override |
| `friendli` | `https://api.friendli.ai/serverless/v1` | 동일 | `FRIENDLI_API_KEY` + `FRIENDLI_TEAM_ID` 헤더 | Nemotron 미호스팅 → 기본 매핑 Super=`Qwen/Qwen3-235B-A22B-Instruct-2507`, Nano=`meta-llama-3.3-70b-instruct` (대체/백업용) |

**Thinking mode 스위치 (중요):** Brev(vLLM)는 `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`, 나머지는 생략 기본. `llm_client.py`가 provider별로 자동 분기.

## OpenClaw workspace 파일

| 파일 | 역할 |
|---|---|
| `extractor/blueprint.yaml` | 수집 에이전트 정의 (skill 7개) |
| `validator/blueprint.yaml` | 검증+종합 에이전트 정의 (skill 3개) |
| `_lib/ari_cli.mjs` | skill들이 공유하는 Python subprocess 헬퍼 |

## 로컬(Mac) 실행 예

```bash
cd /Users/user/Documents/nvidia-hackathon/nvidia-nemotron-hackathon-2026
PYTHONPATH=. ../.venv-nat/bin/python -m ari_agent.cli health
PYTHONPATH=. ../.venv-nat/bin/python -m ari_agent.cli scrape_rss --feed-key simon_willison --limit 3

# node에서 skill 직접 실행
ARI_AGENT_HOME=$(pwd) ARI_PYTHON=$(pwd)/../.venv-nat/bin/python \
  node --input-type=module -e "
    import mod from './extractor/skills/scrape_rss/index.mjs';
    console.log(JSON.stringify(await mod.execute({feed_key:'simon_willison', limit:3}), null, 2));
  "
```

## Brev 실행 (OpenClaw)

```bash
# 전송
git clone <this-repo-url> && cd nvidia-nemotron-hackathon-2026
git checkout feat/openclaw-migration

# Python
pip install -e .

# OpenClaw 연결 (샌드박스 이미 존재하면 바로 connect)
openclaw agent --agent extractor --local \
  -m "Claude Opus 4.7에 대한 evidence를 arxiv/reddit/github에서 각 5건씩 수집해줘"
```

## 참조 파일

- 최초 한국어 리포트 샘플: `../docs/summary-claude-opus-4.7.md`, `../docs/summary-nemotron-3-super.md`
- 공식 가이드: `docs/nemoclaw_guide.md`, `docs/nemo_agent_toolkit_guide.md`, `docs/how-to-deploy-nemotron.md`
