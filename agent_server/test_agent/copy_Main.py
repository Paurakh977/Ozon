"""
agent.py — Mercury-2 calculus tutor with permanent context-window management.

ROOT CAUSE (confirmed from logs):
  - diffusing=True makes Mercury-2 emit intermediate diffusion states as raw
    text. A single response can be 500k–2M chars (4× the entire context window).
  - The previous fix (before_model_callback only) truncated what was SENT to
    the model, but the full oversized response was still STORED in the session.
  - EventsCompactionConfig then crashed trying to summarize those giant events.

PERMANENT FIX — two callbacks:
  1. after_model_callback  → fires after every response, truncates text BEFORE
                             ADK stores it. Keeps session history small forever.
                             (This is the PRIMARY fix.)
  2. before_model_callback → safety net, trims the outgoing request right before
                             it hits the API. Catches anything that slips through.

EventsCompactionConfig is NOT used — it was the proximate crash source.
"""

import os
import logging
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv
load_dotenv()
log = logging.getLogger(__name__)

# Ensure API key is present at import time with a helpful error message.
INCEPTION_API_KEY = os.environ.get("INCEPTION_API_KEY")
if not INCEPTION_API_KEY:
    raise RuntimeError(
        "Environment variable INCEPTION_API_KEY is not set. "
        "Set it in PowerShell: $env:INCEPTION_API_KEY='your_key' and re-run."
    )

# ── Model ─────────────────────────────────────────────────────────────────────

Mercury_2_model = LiteLlm(
    model="openai/mercury-2",
    api_key=INCEPTION_API_KEY,
    api_base="https://api.inceptionlabs.ai/v1",
    max_tokens=8000,
    stream=True,
    extra_body={"diffusing": True, "reasoning_effort": "instant"},
)

# ── Constants ─────────────────────────────────────────────────────────────────
#
# Mercury-2 context window       : 128,000 tokens
# Safe chars to store per turn   :  30,000 chars  ≈  8,500 tokens
#   → 10 stored turns × 30k chars = 300k chars ≈ 86k tokens — fits in 128k ✓
# Total char budget for requests : 280,000 chars  ≈ 80,000 tokens (conservative)

MAX_STORED_CHARS = 30_000
CHAR_BUDGET      = 280_000
CHARS_PER_TOKEN  = 3.5          # conservative for LaTeX/math-heavy content

TRUNCATION_SUFFIX = (
    "\n\n---\n"
    "[Response truncated to fit 128k context window. "
    "Ask a follow-up if you need the rest of this content.]"
)


# ── after_model_callback (PRIMARY FIX) ────────────────────────────────────────

def truncate_response_before_storing(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    Runs immediately after every LLM response, BEFORE ADK saves it to the
    session. Truncates any part that exceeds MAX_STORED_CHARS.

    Why this is the primary fix:
      - Mercury-2 with diffusing=True stores intermediate diffusion steps as
        raw text, inflating a single response to 500k–2M chars.
      - Truncating here means the session history stays small forever, so
        neither the main model nor any compaction summarizer ever receives an
        oversized context.
    """
    if not llm_response or not llm_response.content:
        return None

    modified = False
    for part in llm_response.content.parts or []:
        text = getattr(part, "text", None)
        if text and len(text) > MAX_STORED_CHARS:
            log.warning(
                "after_model_cb: truncating response %d → %d chars",
                len(text), MAX_STORED_CHARS,
            )
            part.text = text[:MAX_STORED_CHARS] + TRUNCATION_SUFFIX
            modified = True

    # Return the modified object so ADK stores the trimmed version.
    # Returning None would leave the original (oversized) version in place.
    return llm_response if modified else None


# ── before_model_callback (SAFETY NET) ────────────────────────────────────────

def trim_request_to_fit_context(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """
    Runs just before every LLM call. If the total chars in the request
    contents exceeds CHAR_BUDGET, drops oldest messages from the front until
    it fits. Always keeps at least the most recent user message.

    Returns None to continue with the (modified) request.
    Returns an LlmResponse only if you want to short-circuit the LLM call
    entirely — we don't want that here, so we always return None.
    """
    contents = llm_request.contents
    if not contents:
        return None

    def total_chars(lst: list) -> int:
        return sum(
            len(p.text)
            for c in lst
            for p in (c.parts or [])
            if getattr(p, "text", None)
        )

    dropped = 0
    while len(contents) > 1 and total_chars(contents) > CHAR_BUDGET:
        contents.pop(0)
        dropped += 1

    if dropped:
        log.warning(
            "before_model_cb: safety net fired — dropped %d message(s). "
            "after_model_cb may not be truncating early enough.",
            dropped,
        )

    log.info(
        "before_model_cb: %d message(s) in request, ~%d estimated tokens",
        len(contents),
        int(total_chars(contents) / CHARS_PER_TOKEN),
    )

    llm_request.contents = contents
    return None  # proceed with modified request


# ── Agent ─────────────────────────────────────────────────────────────────────

root_agent = LlmAgent(
    name="Mercury2_agent",
    model=Mercury_2_model,
    instruction="You are a calculus tutor...",
    description="Calculus tutor",
    after_model_callback=truncate_response_before_storing,  # PRIMARY fix
    before_model_callback=trim_request_to_fit_context,      # safety net
)



# #################


"""
main.py — FastAPI + WebSocket server for the Mercury-2 calculus tutor.

IMPORTANT: No EventsCompactionConfig here.
Context management is handled entirely inside agent.py via:
  - after_model_callback  → truncates responses before storing (primary fix)
  - before_model_callback → trims request before sending (safety net)

EventsCompactionConfig was REMOVED because in the previous attempt it was the
direct crash source: the compaction summarizer received the full oversized
session history and hit the same 128k limit.
"""

import uuid
import logging
import sys

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

import agent

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("server.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("server")

# See callback warnings/info without drowning in LiteLLM debug noise.
# Flip to DEBUG temporarily if you need to trace a failure.
logging.getLogger("google.adk").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)

# ── ADK ───────────────────────────────────────────────────────────────────────

APP_NAME = "math_diffusion_web"

# Plain InMemoryRunner — NO App wrapper, NO EventsCompactionConfig.
# The two callbacks in agent.py are all we need.
runner = InMemoryRunner(agent=agent.root_agent, app_name=APP_NAME)

log.info("Runner ready. Context management via after/before_model_callback.")

# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    turn = 0

    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )
    log.info("SESSION CREATED  user=%s  session=%s", user_id, session.id)

    try:
        while True:
            prompt = await websocket.receive_text()
            turn += 1
            log.info("TURN %d  user=%s  prompt_len=%d", turn, user_id, len(prompt))

            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )

            saw_partial = False

            try:
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session.id,
                    new_message=content,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                ):
                    if not event.content:
                        continue

                    text = "".join(
                        p.text
                        for p in event.content.parts
                        if getattr(p, "text", None)
                    )
                    if not text:
                        continue

                    if getattr(event, "partial", False):
                        await websocket.send_json({"type": "chunk", "text": text})
                        saw_partial = True
                        continue

                    if not saw_partial:
                        await websocket.send_json({"type": "chunk", "text": text})

                log.info("TURN %d DONE  user=%s", turn, user_id)

            except Exception as err:
                log.error(
                    "RUNNER ERROR turn=%d user=%s: %s",
                    turn, user_id, err, exc_info=True,
                )
                await websocket.send_json({"type": "error", "text": str(err)})

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        log.info("DISCONNECT  user=%s  turns=%d", user_id, turn)
    except Exception as e:
        log.error("FATAL  user=%s: %s", user_id, e, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


if __name__ == "__main__":
    print("Server starting → http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)