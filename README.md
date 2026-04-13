# Ozon Calculator

Math calculator with AI agent integration across multiple microservices.

## Architecture

The project consists of 4 main services:
- **Next.js Client**: Frontend application (Port 3000 / https://localhost)
- **NestJS Microservice**: Handles Auth, STT, OCR (Port 3001 / https://localhost)
- **FastAPI Agent Server**: Handles AI Agent workflows (Port 8000)
- **gRPC Server**: Mathematical computations (Port 50051)

## Environment Setup

You can run this application gracefully either via **Local Development (No Docker)** or **Production (Docker Compose)**. 

### Local Development

This runs all services directly on your host machine ports:

1. Database & Redis:
   You need a local PostgreSQL on `5432` and a local Redis on `6379`.

2. Base Environment:
   ```bash
   cp .env.local.example .env
   cd microservice && cp .env.local.example .env && cd ..
   cd server && cp .env.local.example .env && cd ..
   cd service && cp .env.local.example .env && cd ..
   ```
   *Make sure you fill out all the necessary variables in `.env` for each directory.*

3. Start services:
   ```bash
   # Terminal 1 - Microservice
   cd microservice && pnpm install && pnpm run start:dev

   # Terminal 2 - Next.js
   bun install && bun run dev

   # Terminal 3/4 - FastAPI & gRPC (refer to their directories)
   ```

### Production Setup (Docker Compose)

This runs all services through Docker, wrapped with Nginx handling HTTPS traffic directly on `https://localhost`.

1. Base Environment:
   ```bash
   cp .env.production.example .env
   cd microservice && cp .env.production.example .env && cd ..
   cd server && cp .env.production.example .env && cd ..
   cd service && cp .env.production.example .env && cd ..
   ```
   *Make sure you fill out all the necessary variables in `.env` for each directory.*

2. Build and start via Docker:
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

## Nginx Configuration Overview

In production mode, `nginx/nginx.conf` sets up an SSL reverse proxy on port 443 that forwards requests contextually based on the URL paths.
- `https://localhost/api/*` routes to `ozon-microservice:3001`
- `https://localhost/*` routes to `ozonclient:3000`

## OAuth Configurations

When running OAuth (Google/GitHub), the callbacks must map properly. Use `http://localhost:3001` when running locally, and `https://localhost` when running via Docker compose. Remember to continuously update the redirect URL configurations in the respective Google/GitHub development consoles!