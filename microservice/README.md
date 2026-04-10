# Microservice (NestJS)

OCR/STT microservice for parsing files and speech-to-text.

## Requirements

- Node.js 18+
- pnpm

## Setup

```bash
cd microservice
pnpm install
```

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```env
# Server Configuration
PORT=3001

# Your Next.js app URL (required for CORS)
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Deepgram STT Configuration
DEEPGRAM_API_KEY=your_deepgram_key
DEEPGRAM_PROJECT_ID=your_project_id

# Rate limiting
SST_MAX_KEYS_PER_WINDOW=6
SST_KEY_WINDOW_MS=60000

# Mistral OCR Configuration
MISTRAL_API_KEY=your_mistral_key
```

**Required variables:**
- `PORT` - Server port (e.g., 3001)
- `NEXT_PUBLIC_APP_URL` - Your Next.js app URL for CORS
- `DEEPGRAM_API_KEY` - Deepgram API key for speech-to-text
- `DEEPGRAM_PROJECT_ID` - Deepgram project ID
- `MISTRAL_API_KEY` - Mistral API key for OCR
- `SST_MAX_KEYS_PER_WINDOW` - Rate limit max keys per window
- `SST_KEY_WINDOW_MS` - Rate limit window in milliseconds

## Run

```bash
# Development
pnpm run start:dev

# Production
pnpm run build
pnpm run start:prod
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stt` | Get Deepgram temporary key for speech-to-text |
| POST | `/parse` | Parse uploaded file (PDF, images, documents) |

## CORS

CORS is configured to allow requests only from `NEXT_PUBLIC_APP_URL`. Requests from other origins will be blocked.