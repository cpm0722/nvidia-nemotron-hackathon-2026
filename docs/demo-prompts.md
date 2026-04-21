# OpenClaw 대시보드 데모 프롬프트

복사·붙여넣기용. OpenClaw 대시보드에서 Extractor / Validator agent에 그대로 주면 된다.
(`cd ~/.openclaw/workspace` 후 `openclaw dashboard` 실행 전제)

---

## 0) 대시보드 접속

```bash
cd ~/.openclaw/workspace
openclaw dashboard --no-open            # URL + 토큰 출력
# 또는 그냥
openclaw dashboard                      # 브라우저 자동 오픈
openclaw config get gateway.auth.token  # 토큰만 확인
```

Brev에서 띄운 경우 포트 포워딩 필요:
```bash
# 로컬 Mac에서
ssh -L 8080:localhost:<brev-port> <brev-host>
# 그 다음 브라우저 http://localhost:8080?token=...
```

---

## 1) 최소 검증 — Skill 1개만

**에이전트:** Extractor

```
Simon Willison 블로그 RSS에서 최근 3개 글만 가져와줘.
(scrape_rss, feed_key=simon_willison, limit=3)
```

**성공 기준:** 로그에 `scrape_rss` 호출 흔적 + evidence 3건 JSON 출력.
실패하면 skill discovery/LLM provider 문제이므로 더 진행하지 말고 로그 공유.

---

## 2) Extractor 본 쓰임새 — 여러 skill 병렬

**에이전트:** Extractor

```
Claude Opus 4.7에 대한 evidence를 수집해줘.

- arxiv에서 5건
- reddit r/LocalLLaMA, r/MachineLearning에서 5건
- github 이슈에서 5건 (anthropics/anthropic-sdk-python 위주)
- hackernews에서 3건
- 공식·비판 블로그용으로 simon_willison, gary_marcus RSS도 각 5건

모은 뒤 enrich_bodies로 본문까지 채워서 evidence 배열 JSON으로 줘.
```

**성공 기준:** `scrape_arxiv / scrape_reddit / scrape_github / scrape_hackernews / scrape_rss`(2회) + `enrich_bodies` 총 7회 호출. 결과 JSON을 **복사해서 보관**(다음 단계 입력).

---

## 3) Validator — 최종 한국어 리포트

**에이전트:** Validator

```
다음 모델 분석 요청:
- model_name: "Claude Opus 4.7"
- target_url: "https://www.anthropic.com/news/claude-opus-4-7"
- evidence: <위 2단계에서 받은 JSON 붙여넣기>

작업 순서:
1) extract_claims로 target_url에서 공식 주장 추출
2) validate_sources로 evidence 각 항목에 점수
3) synthesize_report로 한국어 cited 마크다운 리포트 생성
```

**성공 기준 — 마크다운에 아래 6개 섹션 전부:**
- `## ⚡ TL;DR` (3줄)
- `## 📊 Claim ↔ Evidence 매트릭스` (표)
- `## 🗣️ 핵심 Quote` (3~5개)
- `## ⚔️ 대립 구도 (공식 vs 커뮤니티)`
- `## 🔎 회의론 신호`
- `## 🎯 Final Assessment`

---

## 4) 다른 타깃으로 한 번 더 (데모 백업)

**에이전트:** Extractor → Validator (같은 흐름)

```
Nemotron-3 Super (nvidia/nemotron-3-super-120b-a12b) 분석해줘.

[Extractor에게]
- arxiv 5건, hf_papers 5건, github 이슈 5건 (NVIDIA/NeMo-Agent-Toolkit, NVIDIA/NemoClaw, NVIDIA/Megatron-LM)
- reddit r/LocalLLaMA 5건
- RSS는 gary_marcus, ai_snake_oil, simon_willison 각 3건

[Validator에게]
- model_name: "Nemotron-3 Super"
- target_url: "https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard"
- evidence: 위 결과
- 3단계(extract_claims → validate_sources → synthesize_report) 그대로
```

중립 유지: Nemotron 찬양 금지. 다른 모델과 같은 잣대 적용(`SOUL.md` 규칙).

---

## 5) 한 방에 보고 싶으면 (수동 체이닝)

대시보드가 agent 간 evidence 전달을 자동화 안 하는 경우:

**탭 1 (Extractor):** 프롬프트 2 실행 → evidence JSON을 파일로 저장
```bash
# 대시보드 응답에서 JSON만 복사해서
cat > /tmp/evidence-claude.json <<'EOF'
<붙여넣기>
EOF
```

**탭 2 (Validator):** 프롬프트 3 실행, evidence 자리에 파일 참조
```
...
- evidence: @/tmp/evidence-claude.json
...
```

(OpenClaw가 `@<path>` 첨부를 지원하지 않으면, 그냥 JSON 본문을 프롬프트에 붙여넣어도 됨.)

---

## 대시보드에서 사고 과정이 사용자에게 그대로 찍히는 경우 (CRITICAL)

**증상:** 에이전트 응답에 `</think>`, `We need to...`, `Let's...`, "Original Request / Early Progress / Context for Suffix" 같은 내부 프롬프트 블록이 그대로 노출.

**원인:** OpenClaw 에이전트의 **자기 LLM**(agent runtime이 skill 선택·오케스트레이션에 쓰는 Nemotron)이 thinking 모드 활성 상태. 우리 `llm_client.py`는 **skill 내부** LLM 호출에만 `enable_thinking=false`를 꽂아줌 — agent runtime 자체 호출에는 영향 없음.

**해결 (Brev에서):**
```bash
# 1) 현재 provider/모델 확인
openshell inference get

# 2) thinking 옵션이 제공되는지 확인
openshell inference set --help | grep -iE 'think|chat.?template|extra'

# 3) 만약 `--extra-body` / `--chat-template-kwargs` 플래그가 있으면:
openshell inference set \
  --provider openai-api \
  --base-url https://model-server-uya78rbya.brevlab.com/v1 \
  --model nvidia/nemotron-3-super-120b-a12b \
  --extra-body '{"chat_template_kwargs":{"enable_thinking":false}}'

# 4) 플래그가 없으면: 다른 provider로 우회
#    (a) NVIDIA Build API — NIM 기본값은 thinking off
openshell inference set --provider nvidia-prod --model nvidia/nemotron-3-super-120b-a12b

#    (b) Anthropic/OpenAI provider — thinking 구조가 달라서 leak 없음
openshell inference set --provider anthropic-prod --model claude-sonnet-4-6
```

**임시 우회:** 대시보드 실패 시, CLI로 우리 skill을 직접 실행하거나 아래 §백업 경로로 한국어 리포트 생성.

---

## 디버깅 체크리스트

- **skill이 안 불리고 그냥 LLM이 대답만 함**
  → `blueprint.yaml`의 `skills:` 리스트 인식 여부 확인.
  → `openclaw agent list` / 대시보드 "Tools/Skills" 패널 확인.

- **"command not found: python"**
  → `_lib/ari_cli.mjs`는 기본으로 `python` 호출. Brev가 `python3`만 있으면:
  ```bash
  export ARI_PYTHON=python3
  ```
  (OpenClaw 서비스 재시작 필요할 수 있음)

- **Nano/Super 모델 404 또는 `does not exist`**
  → `python -m ari_agent.cli health` 로 provider·endpoint 먼저 확인.
  → Brev의 Nano 모델 id는 `nvidia/nemotron-3-nano` (짧은 이름). `llm_client.py`가 자동 처리하지만 override env가 있는지 확인.

- **JS skill이 timeout**
  → scrape_arxiv는 1 req / 3 sec throttle. limit 5 이상이면 15초+ 걸림. 대시보드 타임아웃을 60초 이상으로.

- **Reddit이 403/blocked**
  → OAuth 없이 `.json` fallback 사용 중. User-Agent 블록 가능성. `scrapers/base.py`의 USER_AGENT 조정하거나 해당 scrape 건너뛰기.

---

## 백업 경로 (OpenClaw가 아예 안 돌 때)

Python 직접 실행만으로도 리포트 생성 가능 (에이전트 개입 없음):

```bash
cd ~/.openclaw/workspace
export PYTHONPATH=.

# Extractor 대체: CLI 수동 체이닝
python -m ari_agent.cli scrape_arxiv --query "Claude Opus 4.7" --limit 5 > /tmp/e1.json
python -m ari_agent.cli scrape_reddit --query "Claude Opus 4.7" --subreddits "LocalLLaMA,MachineLearning" --limit 5 > /tmp/e2.json
python -m ari_agent.cli scrape_github --query "Claude Opus 4.7" --repo "anthropics/anthropic-sdk-python" --limit 5 > /tmp/e3.json
# 합치기
python -c "
import json
ev = []
for f in ['/tmp/e1.json','/tmp/e2.json','/tmp/e3.json']:
    ev += json.load(open(f))['evidence']
json.dump({'evidence': ev}, open('/tmp/all.json','w'), ensure_ascii=False)
print('total:', len(ev))
"
# enrich + validate
python -m ari_agent.cli enrich_bodies < /tmp/all.json > /tmp/enriched.json
python -m ari_agent.cli validate_sources < /tmp/enriched.json > /tmp/validated.json

# extract_claims + synthesize_report
python -m ari_agent.cli extract_claims --url "https://www.anthropic.com/news/claude-opus-4-7" > /tmp/claims.json
python -c "
import json
claims = json.load(open('/tmp/claims.json'))
enriched = json.load(open('/tmp/enriched.json'))['evidence']
payload = {'claims': claims.get('claims', []), 'evidence': enriched, 'model_name': 'Claude Opus 4.7'}
print(json.dumps(payload, ensure_ascii=False))
" | python -m ari_agent.cli synthesize_report --max-tokens 6000 > /tmp/report.json

# 최종
python -c "import json; print(json.load(open('/tmp/report.json'))['markdown'])" > /tmp/report.md
cat /tmp/report.md
```

또는 기존 스크립트 그대로:
```bash
python tools/summarize_targets.py   # Claude Opus 4.7 + Nemotron-3 Super 자동 생성
ls docs/summary-*.md                # 기존 Day 1 리포트도 참고 가능
```
