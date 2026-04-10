# Ozone Calculator

Math calculator with AI agent integration.

## Project Structure

- `/` - Next.js application (uses Bun)
- `/microservice` - NestJS OCR/STT microservice (uses pnpm)

## Prerequisites

- Node.js 18+
- Bun (for Next.js)
- pnpm (for microservice)

## Setup

### 1. Microservice (NestJS)

```bash
cd microservice
pnpm install
```

Copy `.env.example` to `.env` and configure:
```env
PORT=3001
NEXT_PUBLIC_APP_URL=http://localhost:3000
DEEPGRAM_API_KEY=your_deepgram_key
DEEPGRAM_PROJECT_ID=your_project_id
MISTRAL_API_KEY=your_mistral_key
SST_MAX_KEYS_PER_WINDOW=6
SST_KEY_WINDOW_MS=60000
```

Run microservice:
```bash
pnpm run start:dev
```

### 2. Next.js Application

```bash
# From root directory
bun install
```

Copy `.env.example` to `.env` and configure:
```env
NEXT_PUBLIC_API_URL=http://localhost:3001
NEXT_PUBLIC_AGENT_WS_URL=ws://localhost:8000/ws
GRPC_SERVER_URL=localhost:50051
```

Run Next.js:
```bash
bun run dev
```

## Environment Variables

### Microservice (.env)
| Variable | Required | Description |
|----------|----------|-------------|
| PORT | Yes | Server port (e.g., 3001) |
| NEXT_PUBLIC_APP_URL | Yes | Next.js app URL for CORS |
| DEEPGRAM_API_KEY | Yes | Deepgram API key |
| DEEPGRAM_PROJECT_ID | Yes | Deepgram project ID |
| MISTRAL_API_KEY | Yes | Mistral API key |
| SST_MAX_KEYS_PER_WINDOW | Yes | Rate limit max keys |
| SST_KEY_WINDOW_MS | Yes | Rate limit window (ms) |

### Next.js (.env)
| Variable | Required | Description |
|----------|----------|-------------|
| NEXT_PUBLIC_API_URL | Yes | Microservice URL |
| NEXT_PUBLIC_AGENT_WS_URL | Yes | Agent WebSocket URL |
| GRPC_SERVER_URL | No | gRPC server URL |

## API Endpoints

### Microservice
- `GET /stt` - Get Deepgram temporary key
- `POST /parse` - Parse uploaded file

## Development

```bash
# Terminal 1 - Microservice
cd microservice && pnpm run start:dev

# Terminal 2 - Next.js
bun run dev
```