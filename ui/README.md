# NeMoBriefing — Chat UI (`nat_ui`)

> **NeMoBriefing** (New Model Briefing) — 새로 나온 AI 모델/프러덕트에 대한
> 공식 벤치마크와 사용자 반응을 빠르게 브리핑해주는 채팅 UI.
> 이름의 `NeMo` 는 백본인 Nemotron 에서 따왔고, 그래서 브랜드 컬러도 NVIDIA 그린입니다.

브라우저 기반의 간단한 채팅 UI 로, 사용자 질의를 e2e 에이전트(port 10000)에
전달하고 최종 마크다운 리포트를 받아서 화면에 렌더링합니다.

> **작업 상태**: UI 기반(프레임) 작업만 먼저 완료된 상태입니다.
> e2e 파이프라인이 아직 작업 중인 동안에도 UI를 독립적으로 개발/테스트할 수
> 있도록 **STUB 모드**를 기본값으로 두었습니다. 다른 에이전트 개발이 끝나면
> `NAT_UI_STUB=0`으로 전환하기만 하면 곧바로 연동됩니다.

---

## 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (static HTML/CSS/JS)                                    │
│    POST /api/chat         ─ 질의 전송, job_id 수령               │
│    GET  /api/chat/{id}    ─ 1.5s 간격 폴링, status 확인          │
│    GET  /api/reports/{n}  ─ 완료된 마크다운 파일 읽기            │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼  (FastAPI, 기본 127.0.0.1:8080)
┌──────────────────────────────────────────────────────────────────┐
│  nat_ui.server                                                   │
│    job 큐잉 + 비동기 실행                                        │
│    ├─ STUB 모드: 샘플 마크다운을 reports/ 에 기록                │
│    └─ LIVE 모드: A2A v0.3 message/send → e2e(10000) 호출         │
│                   결과 마크다운을 reports/*.report.md 로 저장    │
└────────────┬─────────────────────────────────────────────────────┘
             │ (LIVE 모드에서만)
             ▼
┌──────────────────────────────────────────────────────────────────┐
│  agents/e2e A2A 서버 (port 10000)                                │
│    query-generator → collectors × N → reporter                   │
└──────────────────────────────────────────────────────────────────┘
```

비동기 폴링 구조를 택한 이유: e2e 파이프라인은 수 분이 걸릴 수 있어서 HTTP
동기 응답으로 받기엔 부적합합니다. 클라이언트가 `job_id`로 상태를 주기적으로
확인하고, 완료되면 파일을 읽어오는 방식이 가장 단순/안정적입니다.

---

## 파일 구조

```
ui/
├── README.md                     # 이 문서
├── pyproject.toml                # FastAPI + uvicorn + httpx
├── scripts/run.sh                # 개발 서버 실행 스크립트
├── src/nat_ui/
│   ├── __init__.py
│   └── server.py                 # FastAPI 앱 (모든 HTTP 엔드포인트)
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js                    # marked.js + DOMPurify 로 마크다운 렌더링
└── reports/                      # 생성된 *.report.md (gitignored)
```

---

## 실행 방법

### 1) STUB 모드 (기본, 에이전트 없이 UI만 확인)

```bash
cd ui
./scripts/run.sh
# → http://127.0.0.1:8080/ 접속
```

질의를 입력하면 약 1초 후 `reports/<ts>-<slug>.report.md` 형태의 샘플
마크다운이 생성되어 화면에 렌더링됩니다. 헤더 오른쪽 배지가 `STUB`으로
표시됩니다.

### 2) LIVE 모드 (실제 e2e 에이전트 연동)

먼저 프로젝트 루트 README의 순서대로 query-generator, 모든 extractor/validator,
reporter, e2e 에이전트를 각각 띄운 뒤:

```bash
cd ui
NAT_UI_STUB=0 ./scripts/run.sh
```

헤더 배지가 `LIVE`(초록)로 표시되면 실제 e2e 파이프라인으로 붙은 것입니다.

### 환경 변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `NAT_UI_HOST` | `127.0.0.1` | 바인드 주소 |
| `NAT_UI_PORT` | `8080` | 바인드 포트 |
| `NAT_UI_STUB` | `1` | `1` = STUB, `0` = LIVE |
| `NAT_UI_E2E_URL` | `http://localhost:10000` | e2e A2A 서버 URL |
| `NAT_UI_E2E_TIMEOUT` | `600` | A2A 호출 타임아웃(초) |
| `NAT_UI_REPORTS_DIR` | `ui/reports/` | 마크다운 저장 디렉토리 |
| `NAT_UI_STUB_AGENT_MAX` | `10` | collector / reporter 의 최대 대기 시간(초) — STUB 모드에서만 사용 |
| `NAT_UI_QUERY_GEN_DELAY` | `5` | Query Generator phase 의 시각적 고정 지연(초) — STUB/LIVE 공통 |

---

## HTTP API

### `POST /api/chat`

```json
// 요청
{ "query": "GPT5와 Gemma4 비교해줘" }

// 응답
{ "job_id": "6f…" }
```

즉시 `job_id`를 반환하고 백그라운드에서 e2e 호출이 진행됩니다.

### `GET /api/chat/{job_id}`

```json
// pending (agents 가 점점 done 으로 바뀌어간다)
{
  "job_id": "6f…",
  "status": "pending",
  "agents": [
    { "id": "query-generator", "label": "Query Generator", "status": "done" },
    { "id": "arcalive",        "label": "ArcaLive",        "status": "working" },
    { "id": "arxiv",           "label": "arXiv",           "status": "done" },
    { "id": "benchmark",       "label": "Benchmark",       "status": "working" },
    { "id": "geeknews",        "label": "GeekNews",        "status": "working" },
    { "id": "lobsters",        "label": "Lobsters",        "status": "done" },
    { "id": "openai",          "label": "OpenAI Blog",     "status": "working" },
    { "id": "reddit",          "label": "Reddit",          "status": "done" },
    { "id": "reporter",        "label": "Reporter",        "status": "working" }
  ],
  "report_name": null,
  "error": null
}

// done — 모든 에이전트가 done 이 되고 report_name 이 채워진다
{ "job_id": "6f…", "status": "done", "agents": [ ... ],
  "report_name": "1713827400-gpt5.report.md", "error": null }

// error — 실패 시점에 working 이었던 에이전트들은 error 로 전환된다
{ "job_id": "6f…", "status": "error", "agents": [ ... ],
  "report_name": null,
  "error": "RuntimeError: Empty response from e2e agent" }
```

### `GET /api/reports/{name}`

완료된 마크다운 파일의 원문을 `text/markdown`으로 반환합니다. 경로 트래버설은
차단되며, `reports/` 하위의 순수 파일명만 허용됩니다.

### `GET /api/config`

현재 모드(stub/live)와 e2e URL, reports 디렉토리 경로를 반환합니다 (UI
헤더 배지에서 사용).

---

## 제안 카드 (환영 화면)

채팅이 비어 있을 때, 입력창 위 채팅 영역에 최근 공개 모델 4개의 **제안
카드**가 flex 그리드로 뜹니다. 카드를 클릭하면 `"<모델명> <크기>"` 형식의
질의가 **즉시 전송** 되며 (크기가 없는 opus 4.7 은 모델명만), 동시에 카드
영역은 페이드아웃으로 사라지고 에이전트 진행 애니메이션이 시작됩니다.

| 카드 | 크기 | 회사 | 클릭 시 전송되는 질의 |
|---|---|---|---|
| EXAONE 4.5 | 33B | LG AI Research | `exaone 4.5 33B` |
| Gemma 4 | 31B | Google | `gemma 4 31B` |
| Opus 4.7 | — | Anthropic | `opus 4.7` |
| Nemotron 3 Super | 120B | NVIDIA | `nemotron 3 super 120B` |

카드 목록은 [ui/static/app.js](static/app.js) 의 `SUGGESTIONS` 상수에서
수정할 수 있습니다. 로고는 브랜드 컬러 rounded square + inline SVG/텍스트
조합이며, 외부 리소스 의존성 없이 자체 렌더합니다.

---

## 에이전트 진행 표시 (3-phase)

채팅 입력 시 9개의 에이전트가 **3단계로 순차 진행**되는 애니메이션이 뜹니다.
각 phase 는 그룹 박스로 묶여 있고, 이전 phase 가 완료되면 연결 화살표가
점멸하면서 다음 phase 로 활성화가 넘어갑니다.

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

### 진행 순서

1. **입력 즉시** — `query-generator` = `working`, collectors 7개 + reporter = `pending`.
2. **5초 후** (`NAT_UI_QUERY_GEN_DELAY`) — `query-generator` = `done`, 7개 collector 가 일제히 `working` 으로 전이. Query Generator 는 실제 마크다운 파일을 생성하지 **않으며**, 고정 타이머 기반의 순수 시각 연출입니다.
3. collector 의 `<agent_id>.md` 가 `work_dir` 에 나타날 때마다 해당 pill 이 `done` 으로 전이.
4. **7개 collector 모두 done 이 되는 순간** — `reporter` = `working`.
5. `reporter.md` 가 나타나면 `reporter` = `done`. 전체 job = `done`.

### STUB 모드에서의 타이밍

`NAT_UI_STUB=1` 일 때:
- Phase 1 = `NAT_UI_QUERY_GEN_DELAY` 초 대기 (기본 5초)
- Phase 2 = 7개 collector 병렬, 각각 `0 ~ NAT_UI_STUB_AGENT_MAX` 초 랜덤 (기본 10초 cap)
- Phase 3 = reporter 가 `0 ~ NAT_UI_STUB_AGENT_MAX` 초 랜덤

파일 생성 없이 서버 내부 상태만 phase 순서대로 전이시킵니다. 연출만 확인할
때 쓰면 됩니다.

### LIVE 모드 — 파일 기반 진행 표시 (계약)

LIVE 모드에서는 UI 가 실제 e2e A2A 호출과 **phase 애니메이션**을 병렬로
돌립니다. Phase 1 은 고정 5초 타이머고, Phase 2/3 는 아래 파일 신호로
진행됩니다. 계약만 맞추면 자동으로 켜집니다.

#### 1) 작업 디렉토리

UI 가 job 시작 시점에 다음 경로를 `mkdir -p` 합니다:

```
${NAT_UI_REPORTS_DIR}/<job_id>/
```

`job_id` 는 UI 가 발급하는 UUID v4 입니다. 기본 `NAT_UI_REPORTS_DIR` 은
`ui/reports/` 이므로, 예) `ui/reports/6f2c…/`.

#### 2) A2A 메시지 envelope (UI → e2e)

기존처럼 plain text 로 보내지 않고, **JSON 한 덩어리**를 A2A `text` part 에
실어 보냅니다:

```json
{
  "job_id": "6f2c-…",
  "work_dir": "/abs/path/to/ui/reports/6f2c-…",
  "query": "GPT5와 Gemma4 비교해줘"
}
```

e2e 쪽에서는 수신한 텍스트를 **우선 JSON 으로 파싱 시도**하고, 파싱되면
envelope 으로 처리 / 실패하면 (예: 직접 `a2a_client.sh "<query>"` 로 테스트
할 때) 그대로 `query` 로 취급해 주세요. 그래야 UI 없이 CLI 로 돌리는 기존
플로우도 유지됩니다.

e2e 는 `work_dir` 을 모든 하위 에이전트에게 전달해서 각자 결과 파일을
거기에 쓰도록 합니다.

#### 3) 에이전트별 결과 파일 — **Query Generator 는 쓰지 않습니다**

각 collector 와 reporter 가 완료 시점에 다음 파일을 씁니다
(확장자 `.md`, 파일명 = pill ID):

```
<work_dir>/arcalive.md
<work_dir>/arxiv.md
<work_dir>/benchmark.md
<work_dir>/geeknews.md
<work_dir>/lobsters.md
<work_dir>/openai.md
<work_dir>/reddit.md
<work_dir>/reporter.md
```

> **Query Generator 는 파일을 만들지 않습니다.** UI 가 Phase 1 을 고정
> `NAT_UI_QUERY_GEN_DELAY` 초 동안 "연출" 로 보여주고 자동으로 done 으로
> 넘기기 때문에, e2e 쪽에서 `query-generator.md` 를 쓸 필요가 없습니다.

UI 는 0.5초 간격으로 `work_dir` 을 polling 합니다. Phase 2 의 collector
파일들이 생기면 해당 pill 을 `done` 으로 바꾸고, **7개가 전부 done 이 된
순간** Phase 3 로 넘어가서 `reporter` 를 `working` 으로 활성화, `reporter.md`
생성을 기다립니다. 파일 **내용** 은 UI 가 읽지 않으므로 신호용으로만
쓰실 거면 빈 파일이어도 상관없습니다.

#### 4) 최종 리포트

현재는 e2e 의 A2A 응답 텍스트를 최종 마크다운으로 사용합니다
(`ui/reports/<timestamp>-<slug>.report.md` 에 저장). `reporter.md` 는 진행
신호 전용이며 내용은 UI 가 무시합니다. 필요하면 이 동작을 바꿔달라고
말씀해 주세요 — `_run_job` 의 한 줄만 고치면 "reporter.md 를 최종 본문으로
사용" 으로 전환할 수 있습니다.

#### 5) 소프트 실패 처리

e2e 가 성공적으로 응답했는데 일부 파일이 안 떨어진 경우, UI 는 해당 pill
을 **자동으로 done 으로 승격** 시킵니다 (파이프라인이 끝났다는 사실이 각
에이전트의 완료를 이미 함의하므로). 따라서 신호 파일을 빠뜨려도 UI 가
영원히 spinner 로 남지는 않습니다.

반대로 e2e 가 에러를 반환하면, 그 시점에 `pending` 또는 `working` 이던
pill 들은 모두 `error` 로 전이됩니다.

---

## 다른 개발자들을 위한 연동 가이드

### 지금 이 UI가 기대하는 계약 (요약)

| 항목 | 값 |
|---|---|
| A2A 엔드포인트 | `${NAT_UI_E2E_URL}` (기본 `http://localhost:10000`) |
| A2A 메서드 | `message/send` (v0.3), single `text` part |
| 요청 text part | **JSON envelope** `{job_id, work_dir, query}` — 위 "LIVE 모드 계약" 참고 |
| 응답 text part | 그대로 렌더링 가능한 순수 마크다운 문자열 (`<think>` 블록 등 없이) |
| 작업 디렉토리 | UI가 `${NAT_UI_REPORTS_DIR}/<job_id>/` 를 선제 생성 |
| 에이전트별 신호 파일 | `<work_dir>/<pill_id>.md` (9개, 빈 파일 허용) |
| 최종 리포트 저장 위치 | UI가 `${NAT_UI_REPORTS_DIR}/<timestamp>-<slug>.report.md` 로 저장 |

> `*.report.md` 확장자와 `.venv`, `__pycache__` 는 프로젝트 루트
> `.gitignore` 에 이미 잡혀 있습니다. per-job 디렉토리 (`reports/<job_id>/`)
> 는 디버깅용으로 남겨두었으니 필요 시 수동 삭제해 주세요.

### CLI 테스트와의 호환

`agents/e2e/scripts/a2a_client.sh "<query>"` 는 여전히 plain text 로 쿼리를
보냅니다. e2e 의 수신부는 **JSON 파싱 시도 → 실패 시 plain query 로
fallback** 패턴으로 구현해 주세요. 그래야 UI 없이도 기존 CLI 플로우가
깨지지 않습니다.

### 폴링 주기 / job 저장소 / 인증

- 폴링 주기 0.5초는 `_watch_agent_files` 의 `asyncio.sleep(0.5)` 상수입니다.
- job 상태는 프로세스 내 `JOBS: dict` 하나입니다. 다중 워커 / 재시작 시 유실됩니다.
- 인증 / CORS / rate limit 는 아직 없습니다.

데모 용도에는 충분하지만, 프로덕션이나 외부 공개 시 위 세 가지를 점검해
주세요.

### 자주 묻는 질문

- **Q. 여러 사용자가 동시에 써도 되나요?**
  지금은 프로세스 내 `JOBS: dict` 한 곳에만 상태가 있습니다. 데모/로컬 용도로는
  충분하지만, 다중 인스턴스로 띄우려면 Redis 등 외부 저장소로 옮겨야 합니다.

- **Q. 스트리밍으로 진행 상황을 보여줄 수 있나요?**
  e2e 측이 A2A SSE/task streaming 을 지원하면, `/api/chat/{id}` 폴링 대신
  WebSocket/SSE 로 바꿀 수 있습니다. 현재는 단순 폴링입니다.

- **Q. STUB 모드의 가짜 마크다운은 어디서 수정하나요?**
  `ui/src/nat_ui/server.py` 의 `_stub_report()` 함수입니다. 테스트용 샘플을
  추가하고 싶다면 여기에 분기를 더하세요.
