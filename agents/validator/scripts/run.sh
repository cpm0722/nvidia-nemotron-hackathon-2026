#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$AGENT_DIR/configs/config.yml"

INPUT="${1:-Product: Claude Opus 4.7

Source criteria:
Check relevance to queried product.

Scraped data:
{}}"

echo "=== validator direct run ==="
echo "config: $CONFIG_FILE"
echo ""

cd "$AGENT_DIR"
uv run nat run --config_file "$CONFIG_FILE" --input "$INPUT"
