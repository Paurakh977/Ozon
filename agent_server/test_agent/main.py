import uuid
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

import agent

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Runner created once at startup — shared across all connections, no re-init per request
APP_NAME = 'math_diffusion_web'
runner = InMemoryRunner(agent=agent.root_agent, app_name=APP_NAME)


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    user_id = f"user_{uuid.uuid4().hex[:8]}"

    # Session created ONCE per WebSocket connection (i.e. once per conversation)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    try:
        # Keep the connection open — handle every message in the same session
        while True:
            prompt = await websocket.receive_text()

            content = types.Content(
                role='user',
                parts=[types.Part.from_text(text=prompt)],
            )

            saw_partial_text = False

            async for event in runner.run_async(
                user_id=user_id,
                session_id=session.id,
                new_message=content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            ):
                if not event.content:
                    continue

                text = ''.join(part.text for part in event.content.parts if part.text)
                if not text:
                    continue

                if getattr(event, "partial", False):
                    await websocket.send_json({"type": "chunk", "text": text})
                    saw_partial_text = True
                    continue

                if not saw_partial_text:
                    await websocket.send_json({"type": "chunk", "text": text})

            # Signal end-of-turn so the UI can re-enable input
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        print(f"Client {user_id} disconnected.")
    except Exception as e:
        print(f"Error for {user_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


if __name__ == '__main__':
    print("Server starting at http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)