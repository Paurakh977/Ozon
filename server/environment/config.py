import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


WEB_SEARCH_API_KEY = get_env("TAVILY_API_KEY")
MODEL_API_KEY = get_env("MODEL_API_KEY")
MODEL_NAME = get_env("MODEL_NAME")
MODEL_API_BASE = get_env("MODEL_API_BASE_URL")
UVICORN_HOST = get_env("UVICORN_HOST")
JWKS_URL     = get_env("NEST_JWKS_URL")        # https://api.yourdomain.com/api/auth/jwks
JWT_ISSUER   = get_env("NEST_JWT_ISSUER")      # https://api.yourdomain.com
JWT_AUDIENCE = get_env("NEST_JWT_AUDIENCE")    # https://api.yourdomain.com
REDIS_URL    = get_env("REDIS_URL", "redis://localhost:6379")