#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$AGENT_DIR/configs/config.yml"

echo "=== arcalive/validator A2A server ==="
echo "config: $CONFIG_FILE"
echo ""

cd "$AGENT_DIR"
uv run nat a2a serve --config_file "$CONFIG_FILE"
