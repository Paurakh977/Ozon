# ─────────────────────────────────────────────────────────────────
# Stage 1: UV Dependency Builder
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Use the official standalone installer to get `uv`
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# The installer places uv in ~/.local/bin
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────
# Stage 2: Runtime (Python)
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST="0.0.0.0"

EXPOSE 8000

# Run directly via python
CMD ["python", "main.py"]