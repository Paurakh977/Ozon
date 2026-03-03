import uuid
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

# Import the agent you defined in agent.py
import agent

app = FastAPI()

# Mount the 'static' folder so we can serve index.html directly
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    """Redirects the base URL to your beautiful HTML interface."""
    return RedirectResponse(url="/static/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    app_name = 'math_diffusion_web'
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    
    # Initialize the ADK runner and session
    runner = InMemoryRunner(agent=agent.root_agent, app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
    )

    try:
        # Wait for the user's prompt sent via JavaScript
        prompt = await websocket.receive_text()
        
        content = types.Content(
            role='user',
            parts=[types.Part.from_text(text=prompt)],
        )

        saw_partial_text = False

        # Run the agent with SSE Streaming enabled
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            if not event.content:
                continue
            
            # Extract the generated text chunk
            text = ''.join(part.text for part in event.content.parts if part.text)
            if not text:
                continue

            # Stream intermediate partial diffusing chunks back to the browser
            if getattr(event, "partial", False):
                await websocket.send_json({"type": "chunk", "text": text})
                saw_partial_text = True
                continue

            # If SSE gives us the final string without partials
            if not saw_partial_text:
                await websocket.send_json({"type": "chunk", "text": text})

        # Notify the browser that the stream has finished
        await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        print(f"Client {user_id} disconnected.")
    except Exception as e:
        print(f"Error: {e}")
        await websocket.send_json({"type": "error", "text": str(e)})


if __name__ == '__main__':
    # Start the server on port 8000
    print("🚀 Server starting! Open http://127.0.0.1:8000 in your browser.")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)