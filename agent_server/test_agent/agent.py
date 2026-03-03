from google.adk.agents.llm_agent import Agent, LlmAgent
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
import os
from dotenv import load_dotenv
load_dotenv()
api_key=os.environ["INCEPTION_API_KEY"]

Mercury_2_model= LiteLlm(
    model="openai/mercury-2",
    api_key=api_key,
    api_base="https://api.inceptionlabs.ai/v1",
    max_tokens=5000,
    stream=True, 
    extra_body={
        "diffusing": True ,
        "reasoning_effort": "instant",  
    }
)

root_agent = LlmAgent(
    name="Mercury2_agent",
    model=Mercury_2_model,
    instruction="You are a helpful assistant powered by GPT-4o.",
    description="Answer user questions to the best of your knowledge.",
    
)
    
