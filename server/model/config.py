from google.adk.models.lite_llm import LiteLlm
import os
from dotenv import load_dotenv
from environment import MODEL_API_KEY, MODEL_NAME, MODEL_API_BASE

load_dotenv()


model = LiteLlm(
    model=MODEL_NAME,
    api_key=MODEL_API_KEY,
    api_base=MODEL_API_BASE,
    max_tokens=8000,
    stream=True,
    extra_body={
        # "diffusing": True ,
        "reasoning_effort": "high",
    },
)
