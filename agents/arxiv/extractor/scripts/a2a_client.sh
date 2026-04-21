#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"

SERVER_URL="${NAT_A2A_URL:-http://localhost:10011}"
KEYWORD="${1:-nemotron}"

echo "=== extractor-arxiv A2A client test ==="
echo "keyword: $KEYWORD"
echo "server:  $SERVER_URL"
echo ""

cd "$AGENT_DIR"
uv run nat a2a client call --url "$SERVER_URL" --message "$KEYWORD"
