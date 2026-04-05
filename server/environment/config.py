import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f" Missing required environment variable: {name}")
    return value


WEB_SEARCH_API_KEY = get_env("TAVILY_API_KEY")
MODEL_API_KEY = get_env("MODEL_API_KEY")
MODEL_NAME = get_env("MODEL_NAME")
MODEL_API_BASE = get_env("MODEL_API_BASE_URL")
