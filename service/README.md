# gRPC Math Server

gRPC server responsible for executing mathematical computations.

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
| `GRPC_SERVER_URL` | The external/internal address of the gRPC server |
| `GRPC_SERVER_PORT`| The listener port (e.g., `50051`) for the gRPC server |
