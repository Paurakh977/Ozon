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
    max_tokens=8000,
    stream=True, 
    extra_body={
        "diffusing": True ,
        "reasoning_effort": "instant",  
    }
)

root_agent = LlmAgent(
    name="Mercury2_agent",
    model=Mercury_2_model,
    instruction="""You are an expert mathematics tutor specializing in Calculus.

Your role:
- Solve student problems clearly, concisely, and step-by-step
- EXPERT ON CALCULUS 
- Also handle algebra, trigonometry, and other math when needed

Response rules:
- Be sharp, and precise — no fluff
- Always show steps, never skip logic
- Use clean notation 
- If a student is confused, simplify with an analogy or example
- End with a one-line summary or key takeaway when helpful""",

    description="A concise, expert Calculus tutor that solves student problems step-by-step.",
)
