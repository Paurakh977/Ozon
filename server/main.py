import logging
import sys
import time

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

# Runner created once at startup — shared across all connections, no re-init per request
APP_NAME = "math_diffusion_web"
runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)

# ── Heartbeat interval (seconds) ─────────────────────────────────────────────
HEARTBEAT_INTERVAL = 25  # WebSocket ping every 25s to keep connection alive


# ── Lifecycle: pre-warm MCP toolset on startup ───────────────────────────────
@asynccontextmanager
async def lifespan(app):
    """Pre-warm the agent's MCP toolset at server startup.

    The McpToolset with StdioConnectionParams needs to spawn `npx tavily-mcp`
    and do an MCP handshake. By running a lightweight dummy query at startup,
    we pay this cost once — not on the user's first message.
    """
    logger.info("Pre-warming agent (MCP toolset initialization)...")
    t0 = time.monotonic()
    try:
        warmup_session = await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id="__warmup__",
        )
        warmup_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text="2+2")],
        )
        async for _ in runner.run_async(
            user_id="__warmup__",
            session_id=warmup_session.id,
            new_message=warmup_content,
            run_config=RunConfig(streaming_mode=StreamingMode.NONE),
        ):
            pass
        logger.info("Agent pre-warmed successfully in %.1fs", time.monotonic() - t0)
    except Exception as e:
        logger.warning("Agent warmup failed (will init on first request): %s", e)
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

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    logger.info("Client %s connected", user_id)

    # Session created ONCE per WebSocket connection (i.e. once per conversation)
    t0 = time.monotonic()
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )
    logger.info(
        "Session %s created for %s (%.0fms)",
        session.id,
        user_id,
        (time.monotonic() - t0) * 1000,
    )

    # Start heartbeat task
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat(websocket, stop_heartbeat))

    try:
        # Keep the connection open — handle every message in the same session
        while True:
            raw = await websocket.receive_text()

            # Handle pong responses from client (keep-alive acknowledgement)
            if raw.strip() == "__pong__":
                continue

            # Try to parse the message as JSON containing text and expressions state
            client_expressions = []
            try:
                data = json.loads(raw)
                prompt = data.get("text", "")
                client_expressions = data.get("expressions", [])
            except (json.JSONDecodeError, TypeError):
                prompt = raw

            logger.info("[%s] User message: %s", user_id, prompt[:120])

            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )

            # Store frontend state in context var
            state_token = frontend_state_var.set(client_expressions)

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
            token = action_queue_var.set(action_queue)

            try:
                async for event in runner.run_async(
                    user_id=user_id,
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
                        part.text for part in event.content.parts if part.text
                    )
                    if not text:
                        continue

                    if first_text_event:
                        logger.info(
                            "[%s] First text event in %.1fs",
                            user_id,
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
                    user_id,
                    time.monotonic() - t_start,
                )

            except Exception as e:
                logger.error(
                    "[%s] Error during agent run: %s", user_id, e, exc_info=True
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
        logger.info("Client %s disconnected normally.", user_id)
    except Exception as e:
        logger.error("Unexpected error for %s: %s", user_id, e, exc_info=True)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "text": f"Server error: {str(e)}",
                }
            )
        except Exception:
            pass
    finally:
        # Cleanup
        stop_heartbeat.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        logger.info("Cleaned up session for %s", user_id)


if __name__ == "__main__":
    print("Server starting at http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
