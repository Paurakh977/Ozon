#!/bin/bash
set -e

echo "========================================="
echo "Setting up FastAPI Agent Server (Port 8000)"
echo "========================================="

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   or: pip install uv"
    exit 1
fi
echo "✅ uv is installed: $(uv --version)"

# Copy environment file
if [ ! -f .env ]; then
    if [ -f .env.local.example ]; then
        echo "📄 Copying .env.local.example to .env..."
        cp .env.local.example .env
    elif [ -f .env.example ]; then
        echo "📄 Copying .env.example to .env..."
        cp .env.example .env
    fi
    echo "⚠️  Please edit .env and fill in the required values:"
    echo "   Server:"
    echo "   - UVICORN_HOST=0.0.0.0"
    echo "   JWT Verification (from NestJS):"
    echo "   - NEST_JWKS_URL=http://localhost:3001/api/auth/jwks"
    echo "   - NEST_JWT_ISSUER=http://localhost:3001"
    echo "   - NEST_JWT_AUDIENCE=http://localhost:3001"
    echo "   Redis:"
    echo "   - REDIS_URL=redis://localhost:6379"
    echo "   Model Configuration:"
    echo "   - MODEL_NAME=openai/mercury-2"
    echo "   - MODEL_API_BASE_URL=https://api.inceptionlabs.ai/v1"
    echo "   - MODEL_API_KEY"
    echo "   API Keys:"
    echo "   - TAVILY_API_KEY"
    echo "   - GOOGLE_API_KEY"
    echo "   - INCEPTION_API_KEY"
else
    echo "✅ .env already exists"
fi

# Install dependencies with uv
echo "📦 Installing dependencies with uv..."
uv sync

echo ""
echo "========================================="
echo "✅ FastAPI Agent Server setup complete!"
echo "========================================="
echo ""
echo "To start the development server:"
echo "  uv run fastapi dev main.py"
echo ""
echo "The server will be available at: http://localhost:8000"
echo "WebSocket endpoint: ws://localhost:8000/ws"
