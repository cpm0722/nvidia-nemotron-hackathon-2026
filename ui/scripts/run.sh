#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UI_DIR="$(dirname "$SCRIPT_DIR")"

cd "$UI_DIR"

# Defaults — override via env vars.
export NAT_UI_HOST="${NAT_UI_HOST:-127.0.0.1}"
export NAT_UI_PORT="${NAT_UI_PORT:-8080}"
export NAT_UI_STUB="${NAT_UI_STUB:-0}"
export NAT_UI_E2E_URL="${NAT_UI_E2E_URL:-http://localhost:10000}"
export ARI_RUNS_ROOT="${ARI_RUNS_ROOT:-$(cd "$UI_DIR/.." && pwd)/runs}"

echo "=== nat_ui server ==="
echo "host:       $NAT_UI_HOST"
echo "port:       $NAT_UI_PORT"
echo "stub_mode:  $NAT_UI_STUB  (1 = stub, 0 = real e2e agent)"
echo "e2e_url:    $NAT_UI_E2E_URL"
echo "runs_root:  $ARI_RUNS_ROOT"
echo "open:       http://$NAT_UI_HOST:$NAT_UI_PORT/"
echo ""

uv run --with fastapi --with 'uvicorn[standard]' --with httpx \
  python -m nat_ui.server
