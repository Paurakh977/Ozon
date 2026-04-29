#!/bin/bash
set -e

echo "========================================="
echo "Ozon Calculator - Local Development Setup"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a command exists
check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✅ $1 is installed${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 is not installed${NC}"
        return 1
    fi
}

validate_env_file() {
    local file=$1
    local placeholders=("your_" "replace_me" "changeme")
    if [ ! -f "$file" ]; then
        return 0
    fi
    for ph in "${placeholders[@]}"; do
        if grep -q "$ph" "$file"; then
            echo -e "${YELLOW}⚠️  $file contains placeholder values (e.g., '$ph') - please fill in real values${NC}"
            return 1
        fi
    done
    echo -e "${GREEN}✅ $file has no placeholder values${NC}"
    return 0
}

# Step 0: Check prerequisites
echo "📋 Checking prerequisites..."
echo ""
check_command bun
check_command pnpm
check_command uv
echo ""

# Check if PostgreSQL is running (basic check)
if command -v psql &> /dev/null; then
    echo -e "${GREEN}✅ PostgreSQL client found${NC}"
else
    echo -e "${YELLOW}⚠️  PostgreSQL client not found - ensure PostgreSQL is running on port 5432${NC}"
fi

# Check if Redis is running (basic check)
if command -v redis-cli &> /dev/null; then
    echo -e "${GREEN}✅ Redis CLI found${NC}"
else
    echo -e "${YELLOW}⚠️  Redis CLI not found - ensure Redis is running on port 6379${NC}"
fi
echo ""

# Step 1: Copy all environment files
echo "========================================="
echo "Step 1: Setting up environment files"
echo "========================================="
echo ""

# Root .env
if [ ! -f .env ]; then
    if [ -f .env.local.example ]; then
        echo "📄 Copying root .env.local.example to .env..."
        cp .env.local.example .env
    elif [ -f .env.example ]; then
        echo "📄 Copying root .env.example to .env..."
        cp .env.example .env
    fi
else
    echo "✅ Root .env already exists"
fi

# microservice/.env
if [ -d "microservice" ]; then
    if [ ! -f microservice/.env ]; then
        if [ -f microservice/.env.local.example ]; then
            echo "📄 Copying microservice/.env.local.example to microservice/.env..."
            cp microservice/.env.local.example microservice/.env
        elif [ -f microservice/.env.example ]; then
            echo "📄 Copying microservice/.env.example to microservice/.env..."
            cp microservice/.env.example microservice/.env
        fi
    else
        echo "✅ microservice/.env already exists"
    fi
fi

# server/.env
if [ -d "server" ]; then
    if [ ! -f server/.env ]; then
        if [ -f server/.env.local.example ]; then
            echo "📄 Copying server/.env.local.example to server/.env..."
            cp server/.env.local.example server/.env
        elif [ -f server/.env.example ]; then
            echo "📄 Copying server/.env.example to server/.env..."
            cp server/.env.example server/.env
        fi
    else
        echo "✅ server/.env already exists"
    fi
fi

# service/.env
if [ -d "service" ]; then
    if [ ! -f service/.env ]; then
        if [ -f service/.env.local.example ]; then
            echo "📄 Copying service/.env.local.example to service/.env..."
            cp service/.env.local.example service/.env
        elif [ -f service/.env.example ]; then
            echo "📄 Copying service/.env.example to service/.env..."
            cp service/.env.example service/.env
        fi
    else
        echo "✅ service/.env already exists"
    fi
fi

echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Please edit all .env files with your actual API keys before starting services!${NC}"
echo ""

echo "Validating environment files..."
validate_env_file .env
validate_env_file microservice/.env
validate_env_file server/.env
validate_env_file service/.env

# Step 2: Setup each service
echo "========================================="
echo "Step 2: Installing dependencies"
echo "========================================="
echo ""

# Setup Next.js (Root)
echo "📦 Setting up Next.js Client..."
if [ -f "setup_nextjs.sh" ]; then
    bash setup_nextjs.sh
else
    echo "📦 Installing with Bun..."
    bun install
fi
echo ""

# Setup NestJS (microservice)
echo "📦 Setting up NestJS Microservice..."
if [ -d "microservice" ]; then
    cd microservice
    if [ -f "setup.sh" ]; then
        bash setup.sh
    else
        echo "📦 Installing with pnpm..."
        pnpm install
        echo "🗄️  Setting up Prisma..."
        pnpm prisma generate
        pnpm prisma db push
    fi
    cd ..
fi
echo ""

# Setup FastAPI (server)
echo "📦 Setting up FastAPI Agent Server..."
if [ -d "server" ]; then
    cd server
    if [ -f "setup.sh" ]; then
        bash setup.sh
    else
        echo "📦 Installing with uv..."
        uv sync
    fi
    cd ..
fi
echo ""

# Setup gRPC (service)
echo "📦 Setting up gRPC Math Server..."
if [ -d "service" ]; then
    cd service
    if [ -f "setup.sh" ]; then
        bash setup.sh
    else
        echo "📦 Installing with uv..."
        uv sync
    fi
    cd ..
fi
echo ""

# Final instructions
echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "To start all services, you need 4 terminal windows:"
echo ""
echo -e "${GREEN}Terminal 1 - NestJS API (Port 3001):${NC}"
echo "  cd microservice && pnpm run start:dev"
echo ""
echo -e "${GREEN}Terminal 2 - Next.js Client (Port 3000):${NC}"
echo "  bun run dev"
echo ""
echo -e "${GREEN}Terminal 3 - FastAPI Agent (Port 8000):${NC}"
echo "  cd server && uv run fastapi dev main.py"
echo ""
echo -e "${GREEN}Terminal 4 - gRPC Server (Port 50051):${NC}"
echo "  cd service && uv run python grpc_server.py"
echo ""
echo "========================================="
echo "Service URLs after startup:"
echo "========================================="
echo "  Next.js:        http://localhost:3000"
echo "  NestJS API:     http://localhost:3001"
echo "  FastAPI Agent:  http://localhost:8000"
echo "  gRPC Server:    localhost:50051"
echo ""
echo -e "${YELLOW}⚠️  Remember to fill in all API keys in the .env files!${NC}"
echo ""
