#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$AGENT_DIR/configs/config.yml"

KEYWORD="${1:-Codex}"

echo "=== extractor-openai direct run ==="
echo "keyword: $KEYWORD"
echo "config:  $CONFIG_FILE"
echo ""

cd "$AGENT_DIR"
uv run nat run --config_file "$CONFIG_FILE" --input "$KEYWORD"
