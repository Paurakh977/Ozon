from google.adk.models.lite_llm import LiteLlm
import os
from dotenv import load_dotenv
from environment import MODEL_API_KEY, MODEL_NAME, MODEL_API_BASE
from typing import Literal

load_dotenv()

ReasoningEffort = Literal["low", "medium", "high"]

DEFAULT_REASONING_EFFORT: ReasoningEffort = "medium"


def get_model(reasoning_effort: ReasoningEffort | None = None) -> LiteLlm:
    effort = reasoning_effort or DEFAULT_REASONING_EFFORT
    return LiteLlm(
        model=MODEL_NAME,
        api_key=MODEL_API_KEY,
        api_base=MODEL_API_BASE,
        max_tokens=8000,
        stream=True,
        extra_body={
            "reasoning_effort": effort,
        },
    )


model = get_model()
