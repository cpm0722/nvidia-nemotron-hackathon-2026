#!/usr/bin/env bash
# Select which NAT agent to run for this container.
#
# CONFIG_FILE: absolute path to an agent's config.yml inside the image
#              (e.g., /app/agents/collectors/reddit/extractor/configs/config.yml).
# The agent dir (two levels up from the config) is set as CWD so that
# `file://../prompts/...` references in configs resolve correctly.
set -euo pipefail

: "${CONFIG_FILE:?CONFIG_FILE env var must be set to an absolute config.yml path}"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "entrypoint: CONFIG_FILE not found: $CONFIG_FILE" >&2
    exit 1
fi

AGENT_DIR="$(dirname "$(dirname "$CONFIG_FILE")")"
cd "$AGENT_DIR"

exec nat a2a serve --config_file "$CONFIG_FILE"
