# Ozon Calculator - Docker Production Setup Guide

This guide covers deploying the full application stack using Docker Compose. It leverages an Nginx reverse proxy for SSL interception, routing both frontend and backend traffic uniformly over HTTPS, and embeds PostgreSQL & Redis organically into the virtual network.

## Step 1: Generating SSL Certificates
Since Docker routes production traffic entirely via `https://localhost`, you require a locally validated SSL certificate. Ensure the `certs/` folder acts as the repository for Nginx mapping.

1. Ensure `mkcert` is installed (`brew install mkcert` or `choco install mkcert`)
2. Run the generator for `localhost` targeting your `/certs` directory dynamically:
```bash
mkdir certs && cd certs
mkcert -install
mkcert localhost
mv localhost.pem localhost.crt
mv localhost-key.pem localhost.key
cd ..
```

## Step 2: Environment Variables Mapping
Docker loads environment variables locally from each `.env` component and organically binds them directly at compile-time/runtime for services. Copy your `.env.production.example` into standard `.env` constructs targeting Docker namespaces accurately (like `ozon-postgres`).

### A) Root `.env` (Next.js Application)
Run `cp .env.production.example .env` in the root folder.
```env
# NextJS mapped over HTTPS
NEXT_PUBLIC_APP_URL=https://localhost
NEXT_PUBLIC_API_URL=https://localhost

# Websockets routed correctly natively via Secure sockets
NEXT_PUBLIC_AGENT_WS_URL=wss://localhost/ws

# Docker DNS resolution natively calls the inner docker name `ozon-grpc-server` instead of localhost!
GRPC_SERVER_URL=ozon-grpc-server:50051

# Redis Configuration (Required - must match microservice/.env)
# This is used by Docker Compose to configure Redis with password authentication
REDIS_PASSWORD=your_strong_redis_password

DEEPGRAM_API_KEY=your_deepgram_key
MISTRAL_API_KEY=your_mistral_key
```

### B) `microservice/.env` (NestJS Authentication/API Layer)
Run `cp microservice/.env.production.example microservice/.env`.
```env
PORT=3001
NODE_ENV=production

# URLs mapped contextually passing correctly checking the https domain.
NEXT_PUBLIC_APP_URL=https://localhost
BETTER_AUTH_URL=https://localhost
BETTER_AUTH_SECRET=your_32_character_secret

# DATABASE & REDIS dynamically lookup the Docker Container names `ozon-postgres` and `ozon-redis` respectively instead of explicit localhost routing bindings.
DATABASE_URL=postgresql://ozon:ozon69@ozon-postgres:5432/ozon
REDIS_URL=redis://:your_redis_password@ozon-redis:6379
REDIS_PASSWORD=your_redis_password

RESEND_API_KEY=your_resend_api_key
# IMPORTANT: Keep DEV_EMAIL_OVERRIDE active in production until a custom domain is verified through Resend.
DEV_EMAIL_OVERRIDE=your_email@gmail.com

# (Optional) Provide Session / Rate Limiting / 2FA overrides if needed. Eg:
# SESSION_EXPIRES_IN=604800
# TWO_FACTOR_OTP_PERIOD=3
```

### Redis Password Setup (Required)
Redis requires authentication. The password MUST be in **both** `.env` files with the **same value**:
- **Root `.env`**: `REDIS_PASSWORD=your_strong_redis_password` — used by Docker Compose to configure Redis
- **microservice/.env`**: `REDIS_PASSWORD=your_strong_redis_password` and `REDIS_URL=redis://:your_strong_redis_password@ozon-redis:6379` — used by the microservice to connect

Both passwords MUST match exactly.

### C) `server/.env` (FastAPI Agent)
Run `cp server/.env.production.example server/.env`.
```env
UVICORN_HOST=0.0.0.0
MODEL_NAME=openai/mercury-2
MODEL_API_BASE_URL=https://api.inceptionlabs.ai/v1
MODEL_API_KEY=your_model_api_key

TAVILY_API_KEY=your_tavily_key
GOOGLE_API_KEY=your_google_key
INCEPTION_API_KEY=your_inception_key

# JWT verification settings for WS auth handshake
# IMPORTANT: In Docker, localhost points to the agent container itself.
# Use internal service DNS for JWKS fetch; keep issuer/audience as public origin.
NEST_JWKS_URL=http://ozon-microservice:3001/api/auth/jwks
NEST_JWKS_FALLBACK_URLS=https://localhost/api/auth/jwks
NEST_JWKS_VERIFY_SSL=true
NEST_JWT_ISSUER=https://localhost
NEST_JWT_AUDIENCE=https://localhost

# Redis backing for agent rate limits
REDIS_URL=redis://:your_redis_password@ozon-redis:6379
```

### D) `service/.env` (gRPC Math Computation)
Run `cp service/.env.production.example service/.env`.
```env
GRPC_SERVER_URL=localhost:50051
GRPC_SERVER_PORT=50051
```

## Step 3: OAuth Dashboard Configuration
If using Better Auth's OAuth modules, visit the configurations explicitly checking Developer Consoles. Since production maps fully behind Nginx SSL, edit the configurations to:
- **Authorized JavaScript Origin:** `https://localhost`
- **GitHub Callback:** `https://localhost/api/auth/callback/github`
- **Google Callback:** `https://localhost/api/auth/callback/google`

## Step 4: Running the Stack
Docker compose maps natively building instances strictly tracking dependencies (Database -> Backend -> Frontend):

```bash
# Compiles Next.js & Python dependencies caching context gracefully securely
docker compose build --no-cache

# Spin up independent services asynchronously
docker compose up -d
```

### Verification Checks:
If built correctly:
- Open `https://localhost` — UI runs securely without explicit ports mapping properly.
- Open `https://localhost/api/auth/ok` — Native API maps to Status code cleanly fetching the NestJS background natively.
