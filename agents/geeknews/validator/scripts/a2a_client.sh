#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"

SERVER_URL="${NAT_A2A_URL:-http://localhost:10023}"
MESSAGE="${1:-Product: gemma4

Scraped data:
[]}"

echo "=== geeknews/validator A2A client test ==="
echo "server: $SERVER_URL"
echo ""

cd "$AGENT_DIR"
uv run nat a2a client call --url "$SERVER_URL" --message "$MESSAGE"
