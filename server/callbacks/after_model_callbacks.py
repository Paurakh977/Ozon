from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("token_tracker")

SESSION_METADATA_STORE = {}


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
    session = callback_context.session
    session_id = getattr(session, "id", "unknown_session")

    # Initialize session-specific counters in our external store if they don't exist
    if session_id not in SESSION_METADATA_STORE:
        SESSION_METADATA_STORE[session_id] = {
            "turn_number": 0,
            "session_total_tokens": 0,
        }

    # Increment turn number
    SESSION_METADATA_STORE[session_id]["turn_number"] += 1
    turn_number = SESSION_METADATA_STORE[session_id]["turn_number"]
    session_total_tokens = SESSION_METADATA_STORE[session_id]["session_total_tokens"]

    if not llm_response or not llm_response.content:
        log.info("[%s] TURN %02d │ (no content in response)", session_id, turn_number)
        return None

    # ── Collect text from all parts ───────────────────────────────────────────
    full_text = "".join(
        p.text for p in (llm_response.content.parts or []) if getattr(p, "text", None)
    )

    chars = len(full_text)

    # ── Token estimates (three methods) ───────────────────────────────────────
    # 1. Conservative estimate (chars / 3.5) — better for LaTeX/math/code
    conservative_tokens = int(chars / 3.5)

    # 2. Actual usage from the API response (most accurate)
    actual_tokens = None
    usage = getattr(llm_response, "usage_metadata", None)
    if usage:
        actual_tokens = getattr(usage, "candidates_token_count", None) or getattr(
            usage, "completion_tokens", None
        )

    # Use actual tokens if available, otherwise fallback to conservative estimate
    turn_tokens = actual_tokens if actual_tokens else conservative_tokens

    # Update total tokens in our external store
    session_total_tokens += turn_tokens
    SESSION_METADATA_STORE[session_id]["session_total_tokens"] = session_total_tokens

    # ── Build log line ────────────────────────────────────────────────────────
    actual_str = (
        f"{actual_tokens:,}"
        if actual_tokens
        else f"N/A (est used: {conservative_tokens:,})"
    )

    log.info("─" * 65)
    log.info("[%s] TURN %02d RESPONSE STATS", session_id, turn_number)
    log.info("  Characters          : %s", f"{chars:,}")
    log.info("  Tokens (this turn)  : %s", actual_str)
    log.info("  Session total (est) : %s tokens", f"{session_total_tokens:,}")
    log.info(
        "  Context used        : %.1f%% of 128k", (session_total_tokens / 128_000) * 100
    )
    log.info("  Snippet             : %s", full_text[:120].replace("\n", " "))

    # ── Warnings at thresholds ────────────────────────────────────────────────
    if session_total_tokens > 100_000:
        log.warning(
            "⚠️ [%s] TURN %02d: Session estimate %s tokens — CRITICAL, very close to 128k limit!",
            session_id,
            turn_number,
            f"{session_total_tokens:,}",
        )
    elif session_total_tokens > 80_000:
        log.warning(
            "⚠️ [%s] TURN %02d: Session estimate %s tokens — approaching 128k limit.",
            session_id,
            turn_number,
            f"{session_total_tokens:,}",
        )
    elif session_total_tokens > 50_000:
        log.info(
            "ℹ️ [%s] TURN %02d: Session estimate %s tokens — halfway to limit.",
            session_id,
            turn_number,
            f"{session_total_tokens:,}",
        )

    return None  # IMPORTANT: None = store response unchanged
