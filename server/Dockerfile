FROM python:3.12-slim-bookworm AS builder

COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST="0.0.0.0"

EXPOSE 8000

CMD ["python", "main.py"]