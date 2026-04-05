from google.adk.agents.llm_agent import Agent, LlmAgent
from dotenv import load_dotenv

load_dotenv()


from .config import model
from callbacks import log_token_usage
from tools import web_search_mcp_tools

root_agent = LlmAgent(
    name="Mercury2_agent",
    model=model,
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
    # after_model_callback=[log_token_usage],
    tools=[*web_search_mcp_tools],
)
