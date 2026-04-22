# Shared NAT A2A agent image.
#
# Single image, many containers: each container selects which agent to run
# via the CONFIG_FILE env var (path to an agent's config.yml inside the image).
# The entrypoint `cd`s to the agent directory before `nat a2a serve` so that
# `file://../prompts/...` references in configs resolve correctly.
#
# Layered for fast incremental rebuilds:
#   Phase 1 — COPY only pyproject.toml files + uv.lock and run `uv sync`
#             with --no-install-workspace. Heavy (PyPI downloads) but only
#             invalidates when a dependency manifest or uv.lock changes.
#   Phase 2 — COPY the actual libs/ and agents/ source and re-run `uv sync`
#             to editable-link the workspace members. Fast (no downloads);
#             this layer is the one that invalidates on code changes.

FROM python:3.13-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install --no-install-recommends -y curl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /usr/local/bin/

WORKDIR /app

# ─── Phase 1: dependency manifests only ───
COPY pyproject.toml uv.lock ./

COPY libs/ari-core/pyproject.toml        ./libs/ari-core/pyproject.toml
COPY libs/validator-core/pyproject.toml  ./libs/validator-core/pyproject.toml

COPY agents/query-generator/pyproject.toml  ./agents/query-generator/pyproject.toml
COPY agents/reporter/pyproject.toml         ./agents/reporter/pyproject.toml
COPY agents/orchestrator/pyproject.toml     ./agents/orchestrator/pyproject.toml

COPY agents/collectors/arcalive/extractor/pyproject.toml   ./agents/collectors/arcalive/extractor/pyproject.toml
COPY agents/collectors/arcalive/validator/pyproject.toml   ./agents/collectors/arcalive/validator/pyproject.toml
COPY agents/collectors/arxiv/extractor/pyproject.toml      ./agents/collectors/arxiv/extractor/pyproject.toml
COPY agents/collectors/arxiv/validator/pyproject.toml      ./agents/collectors/arxiv/validator/pyproject.toml
COPY agents/collectors/benchmark/extractor/pyproject.toml  ./agents/collectors/benchmark/extractor/pyproject.toml
COPY agents/collectors/benchmark/validator/pyproject.toml  ./agents/collectors/benchmark/validator/pyproject.toml
COPY agents/collectors/geeknews/extractor/pyproject.toml   ./agents/collectors/geeknews/extractor/pyproject.toml
COPY agents/collectors/geeknews/validator/pyproject.toml   ./agents/collectors/geeknews/validator/pyproject.toml
COPY agents/collectors/lobsters/extractor/pyproject.toml   ./agents/collectors/lobsters/extractor/pyproject.toml
COPY agents/collectors/lobsters/validator/pyproject.toml   ./agents/collectors/lobsters/validator/pyproject.toml
COPY agents/collectors/openai/extractor/pyproject.toml     ./agents/collectors/openai/extractor/pyproject.toml
COPY agents/collectors/openai/validator/pyproject.toml     ./agents/collectors/openai/validator/pyproject.toml
COPY agents/collectors/reddit/extractor/pyproject.toml     ./agents/collectors/reddit/extractor/pyproject.toml
COPY agents/collectors/reddit/validator/pyproject.toml     ./agents/collectors/reddit/validator/pyproject.toml

# ari_core is pulled in as an editable path source by each extractor's
# pyproject (not a workspace member), so --no-install-workspace does not
# skip it. Provide an empty stub package so the editable install succeeds;
# Phase 2 copies the real source into the same path.
RUN mkdir -p libs/ari-core/src/ari_core && touch libs/ari-core/src/ari_core/__init__.py

# Heavy step: PyPI download + install. Workspace members (the 16 agents +
# validator-core) are skipped and will be editable-linked in Phase 2.
RUN uv sync --frozen --no-dev --no-install-workspace

# ─── Phase 2: real source + editable workspace install ───
COPY libs/ ./libs/
COPY agents/ ./agents/

RUN uv sync --frozen --no-dev

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Auto-imported by `site.py` at every Python startup — silences NAT's
# 0.0.0.0-bind warning that's irrelevant inside the compose network.
COPY docker/sitecustomize.py /opt/venv/lib/python3.13/site-packages/sitecustomize.py

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
