# syntax=docker/dockerfile:1

# NAPG agent — FastAPI status API + decision orchestrator, served by uvicorn.
# Single-stage on the uv image so the .venv interpreter path stays valid (a
# common multi-stage footgun is copying a venv that points at a python the
# runtime image lacks). The project itself runs from source via `python -m
# napg`, so we install dependencies only (--no-install-project), which also
# sidesteps the ../README.md readme reference in pyproject.toml.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    NAPG_AUDIT_DB=/data/audit.db \
    PATH="/app/.venv/bin:$PATH"

# Dependency layer (cached until the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY napg ./napg
COPY config ./config

# Non-root user; audit DB lives on a mounted Fly volume at /data.
RUN useradd --create-home --uid 10001 napg \
 && mkdir -p /data && chown -R napg:napg /data /app
USER napg

# Internal-only: reached by the frontend over Fly 6PN, which is IPv6-only.
# Bind :: (IPv6 wildcard, dual-stack also serves IPv4) so the .internal address
# resolves and accepts connections; 0.0.0.0 would bind IPv4 only and the 6PN
# connection would be refused.
EXPOSE 8080
CMD ["python", "-m", "napg", "serve", "--host", "::", "--port", "8080"]
