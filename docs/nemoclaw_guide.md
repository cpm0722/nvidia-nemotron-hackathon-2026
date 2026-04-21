# NemoClaw 사용 가이드

NemoClaw는 OpenClaw AI 코딩 에이전트를 NVIDIA의 OpenShell 보안 런타임으로 감싼 오픈소스 레퍼런스 스택이다. 커널 수준 보안(네트워크 접근 제어, 자격증명 격리, 파일시스템 탈출 방지, 프로세스 에스컬레이션 차단)을 유지하면서 AI 에이전트 코드 실행 환경을 제공한다.

**현재 버전:** v0.0.7  
**GitHub:** github.com/NVIDIA/NemoClaw  
**공식 문서:** docs.nvidia.com/nemoclaw/latest/

---

## 시스템 요구사항

| 구성요소 | 최소 | 권장 |
|---------|------|------|
| CPU | 4 vCPU | 8+ vCPU |
| RAM | 8 GB | 16 GB |
| 디스크 | 20 GB | 40 GB |
| OS | Ubuntu 22.04 LTS+ | 동일 |
| Node.js | 22.16+ | Latest |
| Docker | 24+ | Latest |
| Linux Kernel | 5.13+ (Landlock LSM 필요) | — |

> **주의사항**
> - Alpha 소프트웨어 — API 및 동작이 변경될 수 있음
> - 새로 설치된 OpenClaw가 필요 (기존 설치와 충돌 가능)
> - Docker 필수 (Podman alias 미지원)
> - 초기 설정 시 인터넷 연결 필요
> - VPN 사용 시 Telegram API 접근이 차단될 수 있음

---

## 설치

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
source ~/.bashrc   # zsh 사용 시: source ~/.zshrc
```

**제거:**
```bash
curl -fsSL https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/uninstall.sh | bash
```

---

## 빠른 시작

```bash
# 샌드박스 생성 및 연결
nemoclaw my-assistant connect

# OpenClaw TUI 실행
openclaw tui

# 에이전트에 메시지 전송 (CLI)
openclaw agent --agent main --local \
  -m "안녕하세요, 현재 어떤 모델을 사용하고 있나요?" \
  --session-id test

# 샌드박스 상태 확인
nemoclaw my-assistant status
```

---

## 추론 모델 설정

### 지원 프로바이더

| 프로바이더 | 모델 | 설정 명령어 |
|-----------|------|------------|
| NVIDIA Endpoints | nemotron-3-super-120b-a12b | `openshell inference set --provider nvidia-prod --model nvidia/nemotron-3-super-120b-a12b` |
| OpenAI | gpt-4o | `openshell inference set --provider openai-api --model gpt-4o` |
| Anthropic | claude-sonnet-4-6 | `openshell inference set --provider anthropic-prod --model claude-sonnet-4-6` |
| Google Gemini | gemini-2.5-flash | `openshell inference set --provider gemini-api --model gemini-2.5-flash` |

**현재 설정 확인:**
```bash
openshell inference get
```

### 지원 Nemotron 모델

| 모델 | Context | Max Output |
|------|---------|-----------|
| nemotron-3-nano-30b-a3b | 131,072 | 4,096 |
| nemotron-3-super-120b-a12b | 131,072 | 8,192 |
| nemotron-super-49b-v1.5 | 131,072 | 4,096 |
| nemotron-ultra-253b | 131,072 | 4,096 |

---

## 로컬 모델 배포

### vLLM을 이용한 로컬 배포

```bash
pip install vllm
vllm serve nvidia/Nemotron-3-Nano-30B-A3B --host 0.0.0.0 --port 8000
```

**ufw 방화벽 설정 (OpenShell 클러스터 → vLLM 통신 허용):**
```bash
sudo ufw allow proto tcp from 172.18.0.0/16 to any port 8000 comment 'Allow OpenShell cluster to vLLM'
sudo ufw allow proto tcp from 172.17.0.0/16 to any port 8000 comment 'Allow Docker bridge to vLLM'
```

**실험적 vLLM 모드 활성화:**
```bash
NEMOCLAW_EXPERIMENTAL=1 nemoclaw onboard
```

### 로컬 NVIDIA NIM 배포

```bash
NEMOCLAW_EXPERIMENTAL=1 nemoclaw onboard
# 메뉴에서 "Local NVIDIA NIM [experimental]" 선택
```

---

## 네트워크 정책 관리

NemoClaw는 deny-by-default 네트워크 정책을 사용한다. 허용 목록(allowlist)에 등록된 도메인/IP만 에이전트가 접근 가능하며, 재시작 없이 핫 리로드를 지원한다.

```bash
openshell term                          # 실시간 네트워크 요청 모니터링 TUI
nemoclaw <name> policy-list             # 프리셋 목록 확인
nemoclaw <name> policy-add              # 인터랙티브 정책 적용
openshell policy set <policy-file>      # YAML 파일로 정책 동적 업데이트
```

---

## Telegram 봇 연동

에이전트와 Telegram을 통해 상호작용할 수 있다.

### 1단계: 봇 생성

1. Telegram에서 `@BotFather` 검색
2. `/newbot` 전송
3. 표시 이름 설정 (예: "My OpenClaw Assistant")
4. `bot`으로 끝나는 username 설정 (예: `my_openclaw_bot`)
5. 봇 토큰 복사: `123456789:ABCDefgh...`

### 2단계: Chat ID 획득 (권장)

1. `@userinfobot` 또는 `@getidsbot` 검색
2. 아무 메시지 전송 → 본인의 숫자형 Chat ID 확인

### 3단계: cloudflared 설치

```bash
# Ubuntu (amd64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Ubuntu (arm64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

### 4단계: 서비스 시작

```bash
export TELEGRAM_BOT_TOKEN="123456789:ABCDefgh..."
export ALLOWED_CHAT_IDS="123456789"

nemoclaw start    # 서비스 시작
nemoclaw status   # 상태 확인
nemoclaw stop     # 서비스 중지
```

---

## OpenShell 터미널 UI

실시간으로 에이전트의 네트워크 요청을 모니터링하고 동적으로 허용/거부할 수 있다.

```bash
openshell term
```

---

## CLI 전체 명령어 레퍼런스

### 샌드박스 관리

```bash
nemoclaw list                       # 전체 샌드박스 목록 조회
nemoclaw <name> connect             # 샌드박스 연결 (없으면 생성)
nemoclaw <name> status              # 상태 확인
nemoclaw <name> logs [--follow]     # 로그 스트리밍
nemoclaw <name> destroy [--yes]     # 중지 및 삭제
nemoclaw <name> policy-list         # 정책 프리셋 목록 조회
nemoclaw <name> policy-add          # 인터랙티브 정책 적용
```

### 디바이스 페어링

```bash
openclaw devices list               # 대기 중인 페어링 요청 조회
openclaw devices approve <uuid>     # 페어링 승인
```

### 웹 대시보드

```bash
openclaw dashboard                  # 웹 UI 열기
openclaw dashboard --no-open        # URL & 토큰만 출력
openclaw config get gateway.auth.token      # 토큰 조회
openclaw doctor --generate-gateway-token    # 토큰 재생성
```

---

## 보안 기능 요약

| 기능 | 설명 |
|------|------|
| 네트워크 정책 | Deny-by-default + allowlist 기반 아웃바운드 제어 |
| 자격증명 관리 | 호스트 격리 저장 (에이전트 메모리에 노출 안 됨) |
| 파일시스템 격리 | Landlock LSM 경로 격리 |
| 프로세스 제어 | seccomp syscall 제한 |
| 모니터링 | OpenShell TUI 실시간 활동 로깅 |
| 핫 리로드 | 재시작 없이 정책 업데이트 |

---

## 참고 자료

- **Quick Start:** docs.nvidia.com/nemoclaw/latest/get-started/quickstart.html
- **네트워크 정책:** docs.nvidia.com/nemoclaw/latest/reference/network-policies.html
- **추론 옵션:** docs.nvidia.com/nemoclaw/latest/inference/inference-options.html
- **OpenShell 문서:** docs.nvidia.com/openshell/
- **ClawHub (스킬 허브):** clawhub.ai
