# Standalone UI image — separate from the shared NAT agent image on purpose.
#
# The chat UI (ui/src/nat_ui/server.py) is a thin FastAPI app that only needs
# fastapi + uvicorn + httpx. Reusing docker/Dockerfile would drag in the full
# NAT + agents + libs toolchain (hundreds of MB) for no reason — this image
# stays minimal and rebuilds in seconds.
#
# Resulting image: ari/nat-ui:latest (docker-compose.yml tags it explicitly).
# Runtime: uvicorn on 0.0.0.0:8080, reading runs/{run_id}/ from a bind-mount
# and forwarding queries to the orchestrator over the ari-net compose network.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && \
    apt-get install --no-install-recommends -y curl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only the three runtime deps. Pinned lightly to stay in sync with
# ui/pyproject.toml; no uv / workspace dance needed because there are no
# editable workspace members in this image.
RUN pip install \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.27" \
        "httpx>=0.27"

# Copy only the UI — the agent source tree is intentionally left out.
COPY ui/src /app/src
COPY ui/static /app/static

ENV PYTHONPATH=/app/src \
    NAT_UI_HOST=0.0.0.0 \
    NAT_UI_PORT=8080

EXPOSE 8080

CMD ["python", "-m", "nat_ui.server"]
