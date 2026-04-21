import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional, cast
import agent_auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("token_log.log", encoding="utf-8"),
    ],
)

# Ensure token_tracker messages are visible
logging.getLogger("token_tracker").setLevel(logging.INFO)

import asyncio
import uuid
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types
import json

from model import root_agent
from tools import action_queue_var, frontend_state_var
logger = logging.getLogger("server")

# ── Configure agent_auth from env ────────────────────────────────────────────
# In production these come from .env / Docker secrets.
agent_auth.JWKS_URL = os.environ["NEST_JWKS_URL"]
agent_auth.JWKS_FALLBACK_URLS = [
    u.strip()
    for u in os.environ.get("NEST_JWKS_FALLBACK_URLS", "").split(",")
    if u.strip()
]
agent_auth.JWKS_VERIFY_SSL = os.environ.get("NEST_JWKS_VERIFY_SSL", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
agent_auth.JWT_ISSUER = os.environ["NEST_JWT_ISSUER"]
agent_auth.JWT_AUDIENCE = os.environ["NEST_JWT_AUDIENCE"]
agent_auth.REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Runner created once at startup — shared across all connections, no re-init per request
APP_NAME = "math_diffusion_web"
runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)

# ── Heartbeat interval (seconds) ─────────────────────────────────────────────
HEARTBEAT_INTERVAL = 25  # WebSocket ping every 25s to keep connection alive
WS_IDLE_TIMEOUT_SECS = int(os.environ.get("AGENT_WS_IDLE_TIMEOUT_SECS", "1800"))
MAX_WS_MESSAGE_BYTES = int(os.environ.get("AGENT_WS_MAX_MESSAGE_BYTES", "10240"))


# ── Lifecycle: pre-warm MCP toolset on startup ───────────────────────────────
@asynccontextmanager
async def lifespan(app):
    logger.info("Pre-warming agent (MCP toolset initialization)...")
    t0 = time.monotonic()

    # ── Pre-warm JWKS on startup so first request is fast ────────────
    try:
        await agent_auth.get_jwks()
        logger.info("JWKS loaded from %s", agent_auth.JWKS_URL)
    except Exception as e:
        logger.warning("JWKS prefetch failed (will retry on first request): %s", e)

    # ... your existing agent warmup code unchanged ...
    try:
        warmup_session = await runner.session_service.create_session(
            app_name=APP_NAME, user_id="__warmup__",
        )
        warmup_content = types.Content(
            role="user", parts=[types.Part.from_text(text="2+2")],
        )
        async for _ in runner.run_async(
            user_id="__warmup__",
            session_id=warmup_session.id,
            new_message=warmup_content,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            pass
        logger.info("Agent pre-warmed in %.1fs", time.monotonic() - t0)
    except Exception as e:
        logger.warning("Agent warmup failed: %s", e)

    yield
    logger.info("Server shutting down.")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


async def heartbeat(websocket: WebSocket, stop_event: asyncio.Event):
    """Send periodic pings to keep the WebSocket alive and detect dead clients."""
    try:
        while not stop_event.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if stop_event.is_set():
                break
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except asyncio.CancelledError:
        pass


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Prefer proxy headers so anon rate limits are per real client IP behind nginx.
    forwarded_for = websocket.headers.get("x-forwarded-for")
    real_ip = websocket.headers.get("x-real-ip")
    if real_ip:
        client_ip = real_ip.strip()
    elif forwarded_for:
        # Use the right-most hop added by nginx to avoid trusting client-spoofed XFF values.
        forwarded_parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
        client_ip = forwarded_parts[-1] if forwarded_parts else "unknown"
    else:
        client_ip = websocket.client.host if websocket.client else "unknown"
    logger.info("WS connection from %s", client_ip)

    # ── Auth handshake ────────────────────────────────────────────────
    auth_result = await agent_auth.perform_auth_handshake(websocket, client_ip)

    def token_is_expired() -> bool:
        exp = auth_result.token_exp
        if exp is None:
            return False
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return exp <= now_ts

    def coerce_exp(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def downgrade_to_anonymous(reason: str):
        if auth_result.tier == "authenticated":
            logger.info("Downgrading %s from authenticated to anonymous (%s)", client_ip, reason)
        auth_result.user_id = None
        auth_result.email = None
        auth_result.tier = "anonymous"
        auth_result.token_exp = None

    # ── Send auth result back to client ──────────────────────────────
    if not auth_result.allowed:
        await websocket.send_json({
            "type": "rate_limited",
            "message": auth_result.reject_msg,
            "tier": auth_result.tier,
        })
        await websocket.close(code=1008)  # Policy Violation
        return

    await websocket.send_json({
        "type": "auth_ok",
        "tier": auth_result.tier,
        "tokenExp": auth_result.token_exp,
    })

    session_user_id = auth_result.user_id or f"anon_{uuid.uuid4().hex[:8]}"
    logger.info("Session started user=%s tier=%s", session_user_id, auth_result.tier)

    # ── Create agent session ──────────────────────────────────────────
    t0 = time.monotonic()
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=session_user_id,
    )
    logger.info("Session %s created (%.0fms)", session.id, (time.monotonic() - t0) * 1000)

    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat(websocket, stop_heartbeat))

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_IDLE_TIMEOUT_SECS,
                )
            except asyncio.TimeoutError:
                logger.info("WS idle timeout for %s after %ss", session_user_id, WS_IDLE_TIMEOUT_SECS)
                await websocket.close(code=1001)
                break

            if len(raw.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
                await websocket.send_json({
                    "type": "error",
                    "text": f"Message too large (max {MAX_WS_MESSAGE_BYTES} bytes)",
                })
                await websocket.close(code=1009)
                break

            if raw.strip() == "__pong__":
                continue

            # Parse once so we can handle control frames (e.g. auth refresh).
            data = None
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                data = None

            # Allow client to refresh auth tier on an already-open socket.
            if isinstance(data, dict) and data.get("type") == "auth":
                token = data.get("token")
                if token:
                    payload = await agent_auth.verify_jwt(token)
                    payload_dict = payload if isinstance(payload, dict) else None
                    sub = payload_dict.get("sub") if payload_dict else None

                    if sub:
                        auth_result.user_id = sub
                        auth_result.email = payload_dict.get("email") if payload_dict else None
                        auth_result.tier = "authenticated"
                        auth_result.token_exp = coerce_exp(payload_dict.get("exp") if payload_dict else None)
                        logger.info(
                            "WS auth refreshed from %s -> authenticated (%s)",
                            client_ip,
                            sub,
                        )
                    else:
                        # If current auth token is already expired, downgrade tier.
                        # If token is still valid, keep tier to avoid flaky fetch lockouts.
                        if token_is_expired():
                            await downgrade_to_anonymous("auth refresh token invalid and token expired")
                        logger.info(
                            "WS auth refresh token invalid from %s; keeping tier=%s",
                            client_ip,
                            auth_result.tier,
                        )
                else:
                    explicit_logout = bool(data.get("logout"))
                    if explicit_logout:
                        # Explicit sign-out frame should downgrade immediately.
                        await downgrade_to_anonymous("auth refresh explicit logout")
                        logger.info(
                            "WS explicit logout refresh from %s; tier=%s",
                            client_ip,
                            auth_result.tier,
                        )
                    else:
                        # Missing token can happen transiently during auth revalidation.
                        # Keep current tier to avoid false downgrades.
                        logger.info(
                            "WS auth refresh without token from %s; keeping tier=%s",
                            client_ip,
                            auth_result.tier,
                        )

                await websocket.send_json({
                    "type": "auth_ok",
                    "tier": auth_result.tier,
                    "tokenExp": auth_result.token_exp,
                })
                continue

            # If the authenticated token has expired and no valid refresh arrived,
            # immediately downgrade before applying per-prompt limits.
            if auth_result.tier == "authenticated" and token_is_expired():
                await downgrade_to_anonymous("token expired")

            # ── Per-prompt rate limit check ───────────────────────────
            # (Handshake does NOT consume quota; we enforce on every prompt.)
            if auth_result.tier == "authenticated" and auth_result.user_id:
                bucket = f"rl:agent:auth:{auth_result.user_id}"
                limit = agent_auth.AUTH_LIMIT
            else:
                safe_ip = client_ip.replace(":", "_").replace(".", "_")
                bucket = f"rl:agent:anon:{safe_ip}"
                limit = agent_auth.ANON_LIMIT

            allowed, _count = await agent_auth.check_rate_limit(
                bucket, limit, agent_auth.WINDOW_SECS
            )
            if not allowed:
                if auth_result.tier == "anonymous":
                    rl_msg = "Anonymous users can send 3 prompts per minute. Sign in for higher limits."
                else:
                    rl_msg = "Authenticated rate limit reached. Please wait a moment before sending another message."
                await websocket.send_json({
                    "type": "rate_limited",
                    "message": rl_msg,
                    "tier": auth_result.tier,
                })
                continue  # Don't disconnect — let them try again after window resets

            # Try to parse the message as JSON containing text and expressions state
            client_expressions = []
            if isinstance(data, dict):
                prompt = data.get("text", "")
                client_expressions = data.get("expressions", [])
            else:
                prompt = raw

            request_label = auth_result.user_id or session_user_id
            logger.info("[%s] User message: %s", request_label, prompt[:120])

            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )

            # Store frontend state in context var
            state_token = frontend_state_var.set(cast(Any, client_expressions))

            # ── Immediately notify frontend that we're processing ─────────
            # This lets the UI show a "thinking" indicator right away,
            # before the (potentially slow) first streaming event arrives.
            await websocket.send_json({"type": "thinking"})

            # ── Streaming: accumulate text server-side, send full text each time ──
            accumulated_text = ""
            saw_partial_text = False
            t_start = time.monotonic()
            first_text_event = True

            action_queue = []
            token = action_queue_var.set(cast(Any, action_queue))

            try:
                async for event in runner.run_async(
                    user_id=session_user_id,
                    session_id=session.id,
                    new_message=content,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                ):
                    # Check for tool actions
                    if action_queue:
                        while action_queue:
                            action = action_queue.pop(0)
                            await websocket.send_json({"type": "action", **action})

                    if not event.content:
                        continue

                    text = "".join(
                        part.text for part in (event.content.parts or []) if part.text
                    )
                    if not text:
                        continue

                    if first_text_event:
                        logger.info(
                            "[%s] First text event in %.1fs",
                            request_label,
                            time.monotonic() - t_start,
                        )
                        first_text_event = False

                    if getattr(event, "partial", False):
                        # Partial event: append new text and send full accumulated
                        accumulated_text += text
                        await websocket.send_json(
                            {
                                "type": "chunk",
                                "text": accumulated_text,
                            }
                        )
                        saw_partial_text = True
                    else:
                        # Final (non-partial) event: this contains the COMPLETE text
                        if saw_partial_text:
                            # We streamed partials — send final as definitive
                            await websocket.send_json(
                                {
                                    "type": "chunk",
                                    "text": text,
                                }
                            )
                        else:
                            # No streaming happened — send the complete response
                            await websocket.send_json(
                                {
                                    "type": "chunk",
                                    "text": text,
                                }
                            )

                logger.info(
                    "[%s] Agent run completed in %.1fs",
                    request_label,
                    time.monotonic() - t_start,
                )

            except Exception as e:
                logger.error(
                    "[%s] Error during agent run: %s", request_label, e, exc_info=True
                )
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "text": f"Agent error: {str(e)}",
                        }
                    )
                except Exception:
                    pass
            finally:
                action_queue_var.reset(token)
                frontend_state_var.reset(state_token)

            # Signal end-of-turn so the UI can re-enable input
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        logger.info("Client %s disconnected.", session_user_id)
    except Exception as e:
        logger.error("Unexpected error for %s: %s", session_user_id, e, exc_info=True)
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    host = os.getenv("UVICORN_HOST")
    if not host:
        raise ValueError("UVICORN_HOST environment variable is not set")
    print(f"Server starting at http://{host}:8000")
    uvicorn.run("main:app", host=host, port=8000, reload=False)
