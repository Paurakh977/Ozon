
FROM python:3.12-slim-bookworm AS builder

# Install curl, Rust (for fast_math_rs), and the standalone uv binary
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && rm -rf /var/lib/apt/lists/*

# Add  cargo and uv to the path
ENV PATH="/root/.cargo/bin:/root/.local/bin:${PATH}"

WORKDIR /app

# Cache dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY fast_math_rs ./fast_math_rs
COPY *.py ./
COPY engines/ ./engines/
COPY README.md ./

# Syncing the project triggers Maturin to build the Rust wheel automatically inside UV
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

# Install libgomp1 (Required for numpy/scipy at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

#  pre-compiled .venv and source code
COPY --from=builder /app/.venv /app/.venv
COPY *.py ./
COPY engines/ ./engines/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 50051

CMD ["python", "grpc_server.py"]