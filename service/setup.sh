#!/bin/bash
set -e

echo "========================================="
echo "Setting up gRPC Math Server (Port 50051)"
echo "========================================="

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   or: pip install uv"
    exit 1
fi
echo "✅ uv is installed: $(uv --version)"

# Check if Rust/maturin is needed for fast_math_rs
if [ -d "fast_math_rs" ]; then
    echo "🦀 Rust acceleration module detected (fast_math_rs)"
    if ! command -v maturin &> /dev/null; then
        echo "📦 Installing maturin for Rust module build..."
        uv pip install maturin
    fi
    if ! command -v cargo &> /dev/null; then
        echo "⚠️  Rust/Cargo not found. Installing Rust module will be skipped."
        echo "   To enable Rust acceleration, install Rust: https://rustup.rs/"
    fi
fi

# Copy environment file
if [ ! -f .env ] && [ -f .env.local.example ]; then
    echo "📄 Copying .env.local.example to .env..."
    cp .env.local.example .env
else
    echo "✅ .env already exists"
fi

# Install dependencies with uv
echo "📦 Installing dependencies with uv..."
uv sync

# Build Rust module if available
if [ -d "fast_math_rs" ] && command -v cargo &> /dev/null; then
    echo "🦀 Building Rust acceleration module..."
    cd fast_math_rs
    maturin develop --release
    cd ..
fi

# Generate gRPC Python code from proto if needed
if [ -f "../proto/calculator.proto" ]; then
    echo "📡 Proto file found at ../proto/calculator.proto"
    echo "   (gRPC code generation handled in grpc_server.py)"
fi

echo ""
echo "========================================="
echo "✅ gRPC Math Server setup complete!"
echo "========================================="
echo ""
echo "To start the server:"
echo "  uv run python grpc_server.py"
echo ""
echo "The gRPC server will listen on: localhost:50051"
