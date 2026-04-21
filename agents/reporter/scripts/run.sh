#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$AGENT_DIR/configs/config.yml"

PRODUCT="${1:-GPT-5}"

echo "=== reporter direct run ==="
echo "product: $PRODUCT"
echo "config:  $CONFIG_FILE"
echo ""

cd "$AGENT_DIR"
uv run nat run --config_file "$CONFIG_FILE" --input "Product: $PRODUCT

Evidence:
[]"
