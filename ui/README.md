# NeMoBriefing — Chat UI (`nat_ui`)

> **NeMoBriefing** (New Model Briefing) — 새로 나온 AI 모델/프러덕트에 대한
> 공식 벤치마크와 사용자 반응을 빠르게 브리핑해주는 채팅 UI.
> 이름의 `NeMo` 는 백본인 Nemotron 에서 따왔고, 그래서 브랜드 컬러도 NVIDIA 그린입니다.

브라우저 기반 채팅 UI 로, 사용자 질의를 e2e 에이전트(port 10000)에 전달하고
파이프라인 진행 상황을 **Server-Sent Events 로 라이브 스트리밍**해서 각 pill
아래에 "12 items scraped, 8 validated" 같은 세부 상태를 실시간 표시합니다.
최종 마크다운 리포트는 파이프라인 종료 이벤트에 포함된 파일 이름으로 읽어와
화면에 렌더합니다.

**STUB 모드**도 여전히 제공되어 (기본값) 에이전트 없이 렌더 경로만
점검할 수 있습니다 — 가짜 이벤트를 실제와 동일한 버스에 흘려 보냅니다.

---

## 아키텍처

```
┌────────────────────────────────────────────────────────────────────────┐
│  Browser (static HTML/CSS/JS)                                          │
│    POST /api/chat                    ─ 질의 전송, job_id 수령          │
│    EventSource /api/chat/{id}/stream ─ 진행 이벤트 SSE 구독            │
│    GET  /api/reports/{n}             ─ 완료 후 마크다운 본문 읽기      │
└───────────────▲────────────────────┬───────────────────────────────────┘
                │ SSE replay + live  │
                │                    │
┌───────────────┴────────────────────▼───────────────────────────────────┐
│  nat_ui.server  (FastAPI, 기본 0.0.0.0:8080)                            │
│    POST /api/events/{id}          ← 파이프라인 tool 들이 호출          │
│    GET  /api/chat/{id}/stream     → 브라우저가 구독                    │
│    in-memory Job 버스 + 재방송 fan-out                                 │
│    ├─ STUB 모드: 가짜 이벤트를 버스에 주입 (렌더 경로 점검용)          │
│    └─ LIVE 모드: envelope(job_id, event_url 포함)을 e2e 로 전달        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (LIVE 모드)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  agents/e2e A2A 서버 (port 10000)                                      │
│    plan_query → collect_evidence → write_report                        │
│    각 tool / extractor / reporter 가 event_url 로 POST                 │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 파일 구조

```
ui/
├── README.md                     # 이 문서
├── Dockerfile                    # 독립 컨테이너 이미지
├── .dockerignore
├── pyproject.toml                # FastAPI + uvicorn + httpx
├── scripts/run.sh                # 개발 서버 실행 스크립트
├── src/nat_ui/
│   ├── __init__.py
│   └── server.py                 # FastAPI 앱 — 이벤트 버스 + SSE + 기존 REST
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js                    # EventSource 구독 + marked.js 렌더
├── tests/
│   └── integration/test_events_sse.py
└── reports/                      # 생성된 *.report.md (gitignored)
```

---

## 실행 방법

### 1) STUB 모드 (기본, 에이전트 없이 렌더 경로만 점검)

```bash
cd ui
./scripts/run.sh
# → http://127.0.0.1:8080/ 접속
```

렌더 경로를 빠르게 보고 싶으면 타이밍을 짧게:

```bash
NAT_UI_STUB_AGENT_MAX=1 NAT_UI_QUERY_GEN_DELAY=0.5 ./scripts/run.sh
```

헤더 오른쪽 배지가 `STUB` 으로 표시됩니다.

### 2) LIVE 모드 — docker compose (권장)

프로젝트 루트에서:

```bash
docker compose up -d --build
open http://localhost:${UI_HOST_PORT:-8080}
```

UI 컨테이너는 e2e 컨테이너가 healthy 가 된 뒤에야 기동됩니다. 배지가
`LIVE` (초록) 로 표시되면 실제 e2e 파이프라인으로 붙은 것입니다.

### 3) LIVE 모드 — 수동 (개별 프로세스)

먼저 루트 README 순서대로 query-generator, 모든 extractor/validator,
reporter, e2e 에이전트를 띄운 뒤:

```bash
cd ui
NAT_UI_STUB=0 ./scripts/run.sh
```

기본값으로 `NAT_UI_PUBLIC_EVENT_BASE=http://127.0.0.1:8080` 이 사용되므로
파이프라인 모든 프로세스가 같은 호스트에서 도는 경우 그대로 동작합니다.

### 환경 변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `NAT_UI_HOST` | `127.0.0.1` | 바인드 주소 |
| `NAT_UI_PORT` | `8080` | 바인드 포트 |
| `NAT_UI_STUB` | `1` | `1` = STUB, `0` = LIVE |
| `NAT_UI_E2E_URL` | `http://localhost:10000` | e2e A2A 서버 URL |
| `NAT_UI_E2E_TIMEOUT` | `600` | A2A 호출 타임아웃(초) |
| `NAT_UI_REPORTS_DIR` | `ui/reports/` | 마크다운 저장 디렉토리 |
| `NAT_UI_PUBLIC_EVENT_BASE` | `http://$HOST:$PORT` | **다른 컨테이너/프로세스가 이벤트를 POST 하는 대상 URL의 base.** 파이프라인 envelope 의 `event_url` 은 `$BASE/api/events/{job_id}` 로 조립됩니다. docker compose 에서는 `http://ui:8080` 으로 오버라이드. |
| `NAT_UI_STUB_AGENT_MAX` | `10` | STUB 모드에서 collector/reporter 최대 대기 시간(초) |
| `NAT_UI_QUERY_GEN_DELAY` | `5` | STUB/LIVE 공통 — Query Generator phase 의 시각적 최소 지연(초) |

---

## HTTP API

### `POST /api/chat`

```json
// 요청
{ "query": "GPT5와 Gemma4 비교해줘" }

// 응답
{ "job_id": "6f…" }
```

즉시 `job_id` 를 반환하고 백그라운드에서 e2e 호출이 진행됩니다.

### `GET /api/chat/{job_id}/stream` — Server-Sent Events

브라우저가 `EventSource` 로 구독하는 1차 채널. 구독 시점 이전의 이벤트는
전부 즉시 replay, 이후 이벤트는 live push. 파이프라인-레벨 terminal 이벤트
(`{"agent": null, "type": "complete"|"error"}`) 가 전달되는 순간 스트림이
닫힙니다. 30초마다 `: keep-alive` 주석을 보내 프록시 타임아웃을 방지합니다.

이벤트 payload:

```json
{
  "ts": 1713827400.123,
  "job_id": "6f…",
  "agent": "arcalive" | "reporter" | null,
  "phase": "plan" | "collect" | "report" | null,
  "type": "start" | "progress" | "complete" | "error",
  "message": "arcalive: 12 posts scraped, validating…",
  "data": { "scraped": 12, "validated": null }
}
```

- `agent` 가 null 인 이벤트 = 파이프라인 전체의 상태 전환 (phase 시작/종료,
  최종 완료/에러). `data.report_name` 이 최종 complete 이벤트에 담겨옵니다.
- `agent` 가 있으면 UI pill `data-id` 와 매칭되어 해당 pill 의 상태와
  서브텍스트를 갱신합니다.

### `POST /api/events/{job_id}`

파이프라인 tool/agent 가 이벤트를 밀어 넣는 ingestion 엔드포인트. 요청
본문은 위 스키마와 동일한 JSON object. 성공 시 `202 Accepted`, 알 수 없는
`job_id` 는 `404`. 이벤트는 Job 버퍼에 append 되어 replay 용도로 보존되며,
동시에 연결된 모든 SSE 구독자에게 fan-out 됩니다.

### `GET /api/chat/{job_id}` — 폴링 (fallback)

SSE 가 불가능한 환경 (오래된 브라우저, 일부 프록시) 을 위한 1.5초 폴링용.
전체 이벤트 배열 + 최신 pill 상태를 반환합니다.

```json
{
  "job_id": "6f…",
  "status": "pending" | "done" | "error",
  "agents": [ { "id": "...", "label": "...", "status": "..." }, ... ],
  "report_name": "1713827400-gpt5.report.md" | null,
  "error": null,
  "events": [ /* 지금까지 쌓인 이벤트 전체 */ ]
}
```

### `GET /api/reports/{name}`

완료된 마크다운 파일 원문을 `text/markdown` 으로 반환. 경로 트래버설은
차단되며 `reports/` 하위의 순수 파일명만 허용됩니다.

### `GET /api/config`

현재 모드, e2e URL, reports 경로, public event base 를 반환 (UI 헤더
배지에서 사용).

---

## 제안 카드 (환영 화면)

채팅이 비어 있을 때 최근 공개 모델 4개의 **제안 카드**가 flex 그리드로
노출됩니다. 카드를 클릭하면 `"<모델명> <크기>"` 형식의 질의가 즉시 전송되고,
에이전트 진행 애니메이션이 시작됩니다.

| 카드 | 크기 | 회사 | 클릭 시 전송되는 질의 |
|---|---|---|---|
| EXAONE 4.5 | 33B | LG AI Research | `exaone 4.5 33B` |
| Gemma 4 | 31B | Google | `gemma 4 31B` |
| Opus 4.7 | — | Anthropic | `opus 4.7` |
| Nemotron 3 Super | 120B | NVIDIA | `nemotron 3 super 120B` |

카드 목록은 [`static/app.js`](static/app.js) 의 `SUGGESTIONS` 상수에서
수정합니다. 외부 리소스 없이 자체 렌더합니다.

---

## 에이전트 진행 표시 (3-phase)

채팅 입력 시 9개 에이전트가 3단계로 묶여 순차 진행됩니다.

```
┌──────────────────┐     ┌────────────────────────────────────┐     ┌───────────┐
│ 1. Query         │ ──▶ │ 2. Data Collectors (7)             │ ──▶ │ 3. Reporter│
│    Generator     │     │    arcalive / arxiv / benchmark /  │     │           │
│                  │     │    geeknews / lobsters / openai /  │     │           │
│                  │     │    reddit                          │     │           │
└──────────────────┘     └────────────────────────────────────┘     └───────────┘
```

### Pill 상태 (4종)

| 상태 | 표시 | 언제 |
|---|---|---|
| `pending` | 점선 테두리 + 회색 dot, 흐릿 | 아직 자기 phase 가 시작되지 않음 |
| `working` | 회전 스피너 + pop-in 애니메이션 | 현재 phase 활성, 실행 중 |
| `done` | 녹색 체크 (pop-in) | 완료 |
| `error` | 빨간 dot + 빨간 테두리 | 실패 |

### 라이브 서브텍스트

각 pill 아래에 **이벤트 message** 가 덧붙습니다 (예: `arcalive: 12 posts
scraped, validating…` → `arcalive: 7/12 validated`). phase 레벨 이벤트는
phase 헤더의 작은 초록색 italic 줄로 표시됩니다. 모두 SSE 로 푸시되므로
지연이나 폴링 간격 없이 거의 실시간입니다.

### STUB 모드 타이밍

- Phase 1 — `NAT_UI_QUERY_GEN_DELAY` 초 (기본 5)
- Phase 2 — 7개 collector 병렬, 각각 `0 ~ NAT_UI_STUB_AGENT_MAX` 초 랜덤
- Phase 3 — reporter 가 `0 ~ NAT_UI_STUB_AGENT_MAX` 초 랜덤

실제 파이프라인과 동일한 이벤트 시퀀스(start → progress → complete) 를
emit 하므로 프론트엔드 회귀 테스트에 그대로 쓸 수 있습니다.

---

## LIVE 모드 연동 계약 (파이프라인 개발자용)

### 1) UI → e2e envelope

UI 가 A2A `text` part 에 실어 보내는 JSON:

```json
{
  "query": "GPT5와 Gemma4 비교해줘",
  "job_id": "6f2c-…",
  "event_url": "http://ui:8080/api/events/6f2c-…",
  "work_dir": "/app/ui/reports/6f2c-…"
}
```

e2e 의 `plan_query` tool 이 envelope 을 직접 파싱해 `ari_core.events`
contextvars 에 `event_url` / `job_id` 를 세팅합니다. react_agent 의 system
prompt 도 이 envelope 을 그대로 `user_query` 필드에 넣도록 지시하고
있습니다 (`agents/e2e/prompts/system_prompt.txt`).

### 2) 각 에이전트의 책임

| 에이전트 | 이벤트 발행 주체 |
|---|---|
| `plan_query` (tool) | `query-generator` pill 로 start/complete |
| `collect_evidence` (tool) | phase `collect` 의 start/complete (fan-out 시작/집계) |
| 각 extractor | 자기 `SOURCE_NAME` pill 로 start / progress(scraped N) / complete(validated M) / error |
| `write_report` (tool) | phase `report` 의 start/complete (reporter delegation) |
| `reporter` | `reporter` pill 로 start / progress(sources loaded) / complete(chars) / error |

extractor/reporter 는 자신이 받은 envelope 에서 `event_url` / `job_id` 를
parse 해서 `set_event_context` 를 호출해야 UI 에 이벤트가 흐릅니다.
`ari_core.parse_envelope` + `ari_core.set_event_context` + `ari_core.emit_event`
세 가지를 쓰면 됩니다.

### 3) 최종 리포트 전달

모든 tool 이 완료되면 `_run_job` 이 파이프라인-레벨 terminal 이벤트를
발행합니다:

```json
{
  "agent": null,
  "type": "complete",
  "message": "Pipeline finished",
  "data": {"report_name": "1713827400-gpt5.report.md"}
}
```

브라우저는 이 이벤트의 `data.report_name` 으로 `/api/reports/{name}` 을
호출해 마크다운을 받아옵니다. e2e A2A 응답 본문이 여전히 최종 마크다운
원문이며, UI 가 그것을 저장한 뒤 terminal 이벤트를 쏩니다.

### 4) CLI 호환

`agents/e2e/scripts/a2a_client.sh "<query>"` 는 여전히 plain text 쿼리로
보낼 수 있습니다. `ari_core.parse_envelope` 이 JSON 아닌 입력도
graceful 하게 처리(전체 문자열을 `query` 로 취급, streaming context 없음)
하므로 CLI 플로우는 깨지지 않습니다. 이 경우 이벤트 POST 는 전부 no-op
으로 삼켜집니다.

### 5) 에러 처리

- tool 에서 exception 발생 → `_run_job` 이 terminal `error` 이벤트 발행.
- UI 는 `pending`/`working` 이던 pill 을 모두 `error` 로 전환.
- extractor 가 자신만 실패 → 해당 pill `error`, 나머지는 정상 진행.

### 6) 다중 워커 / 재시작

Job 상태는 프로세스 내 `JOBS: dict` 하나입니다. 여러 워커로 띄우려면
Redis 등 외부 저장소로 옮겨야 합니다. 인증 / CORS / rate-limit 는 아직
없습니다 — 내부 네트워크 전용입니다.

---

## 자주 묻는 질문

- **Q. SSE 연결이 끊어지면?**
  프론트엔드 `submitQuery` 가 `sse-failed` 예외를 잡아서 기존 1.5초 폴링
  (`pollJob` + `events` 배열) 으로 자동 전환합니다. 렌더 결과는 동일합니다.

- **Q. 여러 탭에서 같은 job 을 구독해도 되나요?**
  네. 각 SSE 연결마다 독립된 `asyncio.Queue` 가 subscribers 세트에 등록되어
  fan-out 됩니다. 늦게 접속한 탭은 history replay 를 먼저 받고 이어서
  live 이벤트를 받습니다.

- **Q. STUB 모드의 가짜 이벤트는 어디에서 수정하나요?**
  `src/nat_ui/server.py` 의 `_run_stub()` 함수입니다. 실제 파이프라인과
  동일한 이벤트 스키마를 쓰므로 프론트엔드 회귀 테스트용으로 그대로
  활용 가능합니다.
