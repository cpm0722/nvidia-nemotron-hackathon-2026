#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"

SERVER_URL="${NAT_A2A_URL:-http://localhost:10000}"
PRODUCT_NAME="${1:-GPT-5}"

echo "=== extractor-arcalive A2A client test ==="
echo "product: $PRODUCT_NAME"
echo "server:  $SERVER_URL"
echo ""

cd "$AGENT_DIR"
uv run nat a2a client call --url "$SERVER_URL" --message "$PRODUCT_NAME"
