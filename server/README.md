# FastAPI Agent Server

FastAPI backend providing AI agent capabilities with WebSocket support.

## Environment Setup

The application supports two environments. Copy the appropriate example file based on how you are running the service:

### Local Development

For running directly on your machine without Docker:

```bash
cp .env.local.example .env
```

### Production Setup (Docker Compose)

For running via Docker with Nginx reverse proxy:

```bash
cp .env.production.example .env
```

### Required Variables

| Variable | Description |
|----------|-------------|
| `UVICORN_HOST` | Host binding for Uvicorn (e.g. `0.0.0.0`) |
| `MODEL_NAME` | Provide the AI model name (e.g., `openai/mercury-2`) |
| `MODEL_API_BASE_URL` | Base URL for your model API provider |
| `MODEL_API_KEY` | API key to use for the model endpoint |
| `TAVILY_API_KEY` | Tavily API Key for web search |
| `GOOGLE_API_KEY` | Google API Key |
| `INCEPTION_API_KEY` | Inception API Key |
