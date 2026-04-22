# NeMoBriefing chat UI container.
#
# Standalone FastAPI service — not part of the NAT agent uv workspace, so this
# image is intentionally separate from docker/Dockerfile. Minimal surface:
# fastapi + uvicorn + httpx, a small Python package under src/nat_ui, and the
# static assets under static/. Runs on 0.0.0.0:8080 by default; host-side
# port mapping is configured in docker-compose.yml via UI_HOST_PORT.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    NAT_UI_HOST=0.0.0.0 \
    NAT_UI_PORT=8080

RUN apt-get update && \
    apt-get install --no-install-recommends -y curl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app/ui

# ─── Dependency layer (cached until pyproject.toml changes) ───
COPY ui/pyproject.toml ./pyproject.toml
# Setuptools needs a src/ with at least one package dir at install time for
# editable mode; copy the package skeleton before running pip so the layer
# remains cache-friendly.
RUN mkdir -p src/nat_ui && touch src/nat_ui/__init__.py
RUN pip install -e .

# ─── Application layer ───
COPY ui/src/       ./src/
COPY ui/static/    ./static/

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --retries=12 --start-period=10s \
    CMD curl -fsS http://localhost:${NAT_UI_PORT}/api/config > /dev/null || exit 1

CMD ["python", "-m", "nat_ui.server"]
