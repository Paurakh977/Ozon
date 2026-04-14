FROM python:3.12-slim-bookworm AS builder

COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --frozen --no-install-project --no-dev

COPY fast_math_rs ./fast_math_rs
COPY *.py ./
COPY engines/ ./engines/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY *.py ./
COPY engines/ ./engines/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 50051

CMD ["python", "grpc_server.py"]