# Microservice (NestJS)

OCR/STT microservice for parsing files, speech-to-text, and user authentication with Better Auth.

## Requirements

- Node.js 18+
- pnpm
- PostgreSQL (Local or via Docker)
- Redis (Local or via Docker)

## Setup

```bash
cd microservice
pnpm install
```

## Environment Setup

The application supports two environments. Copy the appropriate example file based on how you are running the service:

### Local Development (Directly on host)

For running directly on your machine without Docker (HTTP, explicit ports):

```bash
cp .env.local.example .env
```

### Production Setup (Docker Compose)

For running via Docker with Nginx reverse proxy (HTTPS on localhost):

```bash
cp .env.production.example .env
```

### Required Variables

| Variable | Description |
|----------|-------------|
| `PORT` | Server port (e.g., 3001) |
| `NODE_ENV` | `development` or `production` |
| `NEXT_PUBLIC_APP_URL` | Your Next.js app URL (local: `http://localhost:3000`, prod: `https://localhost`) |
| `BETTER_AUTH_SECRET` | 32+ char secret string (Generate using `openssl rand -base64 32`) |
| `BETTER_AUTH_URL` | Microservice URL (local: `http://localhost:3001`, prod: `https://localhost`) |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string for rate limiting & sessions |
| `RESEND_API_KEY` | Resend API key for sending auth emails |
| `DEV_EMAIL_OVERRIDE` | Email override. Required in prod/local until a custom domain is verified via Resend |
| `SESSION_*`, `TWO_FACTOR_*` | Optional environment variables for session and 2FA timing/limits overrides |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID |
| `GOOGLE_CLIENT_SECRET`| Google OAuth Client Secret |
| `GITHUB_CLIENT_ID` | GitHub OAuth Client ID |
| `GITHUB_CLIENT_SECRET`| GitHub OAuth Client Secret |
| `DEEPGRAM_API_KEY` | Deepgram API key for STT |
| `DEEPGRAM_PROJECT_ID` | Deepgram Project ID |
| `MISTRAL_API_KEY` | Mistral API key for OCR |

## OAuth Setup & Configuration

You must register an OAuth application with both Google and GitHub. The callback URLs depend on your environment.

### Google OAuth
Configure your app in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
- **Local Dev Callback:** `http://localhost:3001/api/auth/callback/google`
- **Production Callback:** `https://localhost/api/auth/callback/google`

### GitHub OAuth
Configure your app in [GitHub Developer Settings](https://github.com/settings/developers):
- **Local Dev Callback:** `http://localhost:3001/api/auth/callback/github`
- **Production Callback:** `https://localhost/api/auth/callback/github`

*Note: Update these corresponding URLs in the respective consoles when switching between local and production modes!*

## Database & Redis

For Local Dev:
- Database: `postgresql://ozon:ozon69@localhost:5432/ozon`
- Redis: `redis://localhost:6379`

For Production (Docker):
- Database: `postgresql://ozon:ozon69@ozon-postgres:5432/ozon`
- Redis: `redis://ozon-redis:6379`

## Run

```bash
# Development
pnpm run start:dev

# Production
pnpm run build
pnpm run start:prod
```