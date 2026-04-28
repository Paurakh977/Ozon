#!/bin/bash
set -e

echo "========================================="
echo "Setting up Next.js Client (Port 3000)"
echo "========================================="

# Check if bun is installed
if ! command -v bun &> /dev/null; then
    echo "❌ Bun is not installed. Please install Bun first:"
    echo "   curl -fsSL https://bun.sh/install | bash"
    exit 1
fi
echo "✅ Bun is installed: $(bun --version)"

# Copy environment file
if [ ! -f .env ] && [ -f .env.local.example ]; then
    echo "📄 Copying .env.local.example to .env..."
    cp .env.local.example .env
    echo "⚠️  Please edit .env and fill in the required API keys:"
    echo "   - DEEPGRAM_API_KEY"
    echo "   - MISTRAL_API_KEY"
else
    echo "✅ .env already exists"
fi

# Install dependencies
echo "📦 Installing dependencies with Bun..."
bun install

echo ""
echo "========================================="
echo "✅ Next.js Client setup complete!"
echo "========================================="
echo ""
echo "To start the development server:"
echo "  bun run dev"
echo ""
echo "The app will be available at: http://localhost:3000"
