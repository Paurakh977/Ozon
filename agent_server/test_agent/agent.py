from google.adk.agents.llm_agent import Agent, LlmAgent
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams
from mcp import StdioServerParameters
import os
from dotenv import load_dotenv
load_dotenv()


import logging
from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
api_key=os.environ["INCEPTION_API_KEY"]



"""
token_logger.py — Drop-in after_model_callback that logs token usage per turn.

Usage in agent.py:
    from token_logger import log_token_usage
    
    root_agent = LlmAgent(
        ...
        after_model_callback=log_token_usage,
    )
"""


log = logging.getLogger("token_tracker")

def log_token_usage(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    Fires after every model response. Logs:
      - Turn number
      - Response chars and estimated tokens
      - Cumulative session token total
      - A warning if you're approaching 128k limit
    
    Returns None so ADK stores the response completely unchanged.
    """
    # ── Context Extraction ────────────────────────────────────────────────────
    # In ADK, callback_context.session provides session details
    session = callback_context.session
    session_id = getattr(session, "id", "unknown_session")
    
    # We use session metadata to track totals correctly across turns in a shared process
    if not hasattr(session, "metadata") or session.metadata is None:
        session.metadata = {}
    
    # Initialize session-specific counters in metadata if they don't exist
    turn_number = session.metadata.get("turn_number", 0) + 1
    session_total_tokens = session.metadata.get("session_total_tokens", 0)
    
    session.metadata["turn_number"] = turn_number

    if not llm_response or not llm_response.content:
        log.info("[%s] TURN %02d │ (no content in response)", session_id, turn_number)
        return None

    # ── Collect text from all parts ───────────────────────────────────────────
    full_text = "".join(
        p.text
        for p in (llm_response.content.parts or [])
        if getattr(p, "text", None)
    )

    chars = len(full_text)

    # ── Token estimates (three methods) ───────────────────────────────────────
    # 1. Rough estimate (chars / 4) — fast, works for plain English
    rough_tokens = chars // 4

    # 2. Conservative estimate (chars / 3.5) — better for LaTeX/math/code
    conservative_tokens = int(chars / 3.5)

    # 3. Actual usage from the API response (most accurate)
    actual_tokens = None
    usage = getattr(llm_response, "usage_metadata", None)
    if usage:
        actual_tokens = getattr(usage, "candidates_token_count", None) \
                     or getattr(usage, "completion_tokens", None)

    # Use actual tokens if available, otherwise fallback to conservative estimate
    turn_tokens = actual_tokens if actual_tokens else conservative_tokens
    session_total_tokens += turn_tokens
    session.metadata["session_total_tokens"] = session_total_tokens

    # ── Build log line ────────────────────────────────────────────────────────
    actual_str = f"{actual_tokens:,}" if actual_tokens else "N/A (est used: " + f"{conservative_tokens:,})"

    log.info("─" * 65)
    log.info("[%s] TURN %02d RESPONSE STATS", session_id, turn_number)
    log.info("  Characters          : %s", f"{chars:,}")
    log.info("  Tokens (this turn)  : %s", actual_str)
    log.info("  Session total (est) : %s tokens", f"{session_total_tokens:,}")
    log.info("  Context used        : %.1f%% of 128k", (session_total_tokens / 128_000) * 100)
    log.info("  Snippet             : %s", full_text[:120].replace("\n", " "))

    # ── Warnings at thresholds ────────────────────────────────────────────────
    if session_total_tokens > 100_000:
        log.warning(
            "⚠️ [%s] TURN %02d: Session estimate %s tokens — CRITICAL, very close to 128k limit!",
            session_id, turn_number, f"{session_total_tokens:,}"
        )
    elif session_total_tokens > 80_000:
        log.warning(
            "⚠️ [%s] TURN %02d: Session estimate %s tokens — approaching 128k limit.",
            session_id, turn_number, f"{session_total_tokens:,}"
        )
    elif session_total_tokens > 50_000:
        log.info(
            "ℹ️ [%s] TURN %02d: Session estimate %s tokens — halfway to limit.",
            session_id, turn_number, f"{session_total_tokens:,}"
        )

    return None  # IMPORTANT: None = store response unchanged


    return None  # IMPORTANT: None = store response unchanged



Mercury_2_model= LiteLlm(
    model="openai/mercury-2",
    api_key=api_key,
    api_base="https://api.inceptionlabs.ai/v1",
    max_tokens=8000,
    stream=True, 
    extra_body={
        # "diffusing": True ,
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
    after_model_callback=[log_token_usage],
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=[
                        "-y",
                        "tavily-mcp@latest",
                    ],
                    env={
                        "TAVILY_API_KEY": os.environ["TAVILY_API_KEY"],
                        "DEFAULT_PARAMETERS":DEFAULT_PARAMS  ,
                    }
                ),
                timeout=30,
            ),
        )
    ],
)
