#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$AGENT_DIR/configs/config.yml"

PRODUCT_NAME="${1:-gemma4}"

echo "=== collector/lobsters direct run ==="
echo "product: $PRODUCT_NAME"
echo "config:  $CONFIG_FILE"
echo ""

cd "$AGENT_DIR"
uv run nat run --config_file "$CONFIG_FILE" --input "$PRODUCT_NAME"
