# Ozon Calculator - Local Development Setup Guide

This guide ensures environments map gracefully for independent component execution spanning the complete frontend to backend loops organically bypassing Docker, Nginx and explicit HTTPS integrations entirely using direct localhost addresses securely.

## Step 1: External Database Setup
Since you aren't deploying PostgreSQL or Redis through Docker Compose, you must provide your own locally hosted instances tracking explicitly against generic port parameters cleanly (`5432` for Postgres, `6379` for Redis). Ensure roles are defined natively.

## Step 2: Automated Setup with Shell Scripts (Recommended)
Instead of manually copying environment files and installing dependencies, you can use the provided shell scripts to automate the entire local setup process. All scripts support both `.env.local.example` and `.env.example` files, and validate that no placeholder values (e.g., `your_deepgram_key`) remain in your environment files.

### Available Scripts
| Script | Purpose |
|--------|---------|
| `local_setup.sh` | Main orchestrator for all services. Checks prerequisites (bun, pnpm, uv, PostgreSQL, Redis), copies all env files from examples, installs dependencies for all services, runs Prisma setup for NestJS, and validates env configurations. |
| `setup_nextjs.sh` | Sets up the Next.js Client (root). Copies `.env` from example, installs Bun dependencies. |
| `microservice/setup.sh` | Sets up the NestJS Microservice. Copies `.env` from example, installs pnpm dependencies, runs Prisma generate and db push. |
| `server/setup.sh` | Sets up the FastAPI Agent Server. Copies `.env` from example, installs Python dependencies via `uv`. |
| `service/setup.sh` | Sets up the gRPC Math Server. Copies `.env` from example, installs Python dependencies via `uv`. |

### Quick Start (All Services)
Run this command from the project root to set up everything automatically:
```bash
bash local_setup.sh
```

### Individual Service Setup
To set up a specific service manually:
```bash
# Next.js Client
bash setup_nextjs.sh

# NestJS Microservice
cd microservice && bash setup.sh && cd ..

# FastAPI Agent
cd server && bash setup.sh && cd ..

# gRPC Server
cd service && bash setup.sh && cd ..
```

## Step 3: Environment Variables (Manual Setup)
If you prefer to set up environment variables manually instead of using the automated shell scripts, follow the steps below. Local development expects explicit local ports tracking standard context logic smoothly bypassing Nginx. Ensure you populate variables according to `.env.local.example`.

### A) Root `.env` (Next.js Application)
Run `cp .env.local.example .env` in the root folder.
```env
# Next.js targets port 3000 mapping organically
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Explicit mapping targeting NestJS directly at Port 3001
NEXT_PUBLIC_API_URL=http://localhost:3001

# WebSocket routing independently rendering across port 8000 gracefully 
NEXT_PUBLIC_AGENT_WS_URL=ws://localhost:8000/ws

# Math Server bounds locally explicitly mapped directly
GRPC_SERVER_URL=localhost:50051

DEEPGRAM_API_KEY=your_deepgram_key
MISTRAL_API_KEY=your_mistral_key
```

### B) `microservice/.env` (NestJS Authentication/API Layer)
Run `cp microservice/.env.local.example microservice/.env`.
```env
PORT=3001
NODE_ENV=development
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Better-Auth settings bypass SSL explicitly 
BETTER_AUTH_SECRET=your_32_character_secret
BETTER_AUTH_URL=http://localhost:3001

# Databases mapped explicitly fetching Localhost context inherently
DATABASE_URL=postgresql://ozon:ozon69@localhost:5432/ozon
REDIS_URL=redis://localhost:6379

RESEND_API_KEY=your_resend_api_key

# Safely catch and override ALL development emails forwarding properly checking locally 
DEV_EMAIL_OVERRIDE=your_test_email@domain.com

# (Optional) Provide Session / Rate Limiting / 2FA overrides if needed. Eg:
# SESSION_EXPIRES_IN=604800
# TWO_FACTOR_OTP_PERIOD=3
```

### C) `server/.env` (FastAPI Agent)
Run `cp server/.env.local.example server/.env`.
```env
UVICORN_HOST=0.0.0.0
MODEL_NAME=openai/mercury-2
MODEL_API_BASE_URL=https://api.inceptionlabs.ai/v1
MODEL_API_KEY=your_model_api_key

TAVILY_API_KEY=your_tavily_key
GOOGLE_API_KEY=your_google_key
INCEPTION_API_KEY=your_inception_key

# JWT verification settings for WS auth handshake
NEST_JWKS_URL=http://localhost:3001/api/auth/jwks
NEST_JWT_ISSUER=http://localhost:3001
NEST_JWT_AUDIENCE=http://localhost:3001

# Redis backing for agent rate limits
REDIS_URL=redis://localhost:6379
```

### D) `service/.env` (gRPC Math Environment)
Run `cp service/.env.local.example service/.env`.
```env
GRPC_SERVER_URL=localhost:50051
GRPC_SERVER_PORT=50051
```

## Step 4: OAuth Context Re-configuration
You must map variables appropriately against Google/GitHub Developer controls strictly defining Local contexts omitting SSL requirements inherently capturing standard localhost tracking logic:
- **Authorized JavaScript Origin:** `http://localhost:3000` & `http://localhost:3001`
- **GitHub Callback:** `http://localhost:3001/api/auth/callback/github`
- **Google Callback:** `http://localhost:3001/api/auth/callback/google`

## Step 5: Connecting the Prisma Mapping
Before starting your NestJS context gracefully, ensure Prisma logic has configured structural tables properly targeting the explicitly bound explicit Database natively. Note: The `local_setup.sh` automated script already runs these commands for you.
```bash
cd microservice
pnpm install
pnpm prisma db push
pnpm prisma generate
```

## Step 6: Booting Up Independent Servers
Ensure you map four distinctive console instances maintaining application parity accurately tracking logic components natively bypassing container dependencies natively. Note: Dependencies are automatically installed when using the provided shell scripts (`local_setup.sh` or individual service scripts). The scripts use `uv` (faster than `pip`) for Python dependencies.

#### Terminal1 - NestJS API
```bash
cd microservice 
pnpm run start:dev
```

#### Terminal2 - Next.js UI Context
```bash
bun run dev
```

#### Terminal3 - FastAPI AI Agent
```bash
cd server
uv run fastapi dev main.py
```

#### Terminal4 - gRPC Mathematics Backend
```bash
cd service
uv run python grpc_server.py
```

#### Terminal 2 - Next.js UI Context
```bash
bun install
bun run dev
```

#### Terminal 3 - FastAPI AI Agent
```bash
cd server
pip install -r requirements.txt
fastapi dev main.py
```

#### Terminal 4 - gRPC Mathematics Backend
```bash
cd service
pip install -r requirements.txt
python grpc_server.py
```
