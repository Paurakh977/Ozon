#!/bin/bash
set -e

echo "========================================="
echo "Setting up NestJS Microservice (Port 3001)"
echo "========================================="

# Check if pnpm is installed
if ! command -v pnpm &> /dev/null; then
    echo "❌ pnpm is not installed. Please install pnpm first:"
    echo "   npm install -g pnpm"
    exit 1
fi
echo "✅ pnpm is installed: $(pnpm --version)"

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
    echo "   - PORT=3001"
    echo "   - NODE_ENV=development"
    echo "   Better Auth:"
    echo "   - BETTER_AUTH_SECRET (32+ character secret, generate: openssl rand -base64 32)"
    echo "   - BETTER_AUTH_URL=http://localhost:3001"
    echo "   Database:"
    echo "   - DATABASE_URL=postgresql://ozon:ozon69@localhost:5432/ozon"
    echo "   Redis:"
    echo "   - REDIS_URL=redis://localhost:6379"
    echo "   Email (Resend):"
    echo "   - RESEND_API_KEY"
    echo "   - DEV_EMAIL_OVERRIDE"
    echo "   OAuth (optional):"
    echo "   - GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET"
    echo "   - GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET"
    echo "   API Keys:"
    echo "   - DEEPGRAM_API_KEY"
    echo "   - MISTRAL_API_KEY"
else
    echo "✅ .env already exists"
fi

# Install dependencies
echo "📦 Installing dependencies with pnpm..."
pnpm install

# Prisma setup
echo "🗄️  Setting up Prisma..."
pnpm prisma generate
pnpm prisma db push

echo ""
echo "========================================="
echo "✅ NestJS Microservice setup complete!"
echo "========================================="
echo ""
echo "To start the development server:"
echo "  pnpm run start:dev"
echo ""
echo "The API will be available at: http://localhost:3001"
echo "JWKS endpoint: http://localhost:3001/api/auth/jwks"
