# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");

import asyncio
import uuid
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.cli.utils import logs
from google.adk.runners import InMemoryRunner
from google.genai import types

import agent  # This imports your existing agent (with diffusion enabled)

load_dotenv(override=True)
logs.log_to_tmp_folder()

app = FastAPI()

# ---------------------------------------------------------
# HTML & CSS FRONTEND
# ---------------------------------------------------------
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Inception Diffusion Agent</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1e1e2e; color: #cdd6f4; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
        #chat-container { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .message { max-width: 80%; padding: 12px 16px; border-radius: 8px; line-height: 1.5; word-wrap: break-word; }
        .user-message { align-self: flex-end; background-color: #89b4fa; color: #11111b; }
        .ai-message { align-self: flex-start; background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }
        /* A subtle glow effect to represent the diffusion process */
        .diffusing { text-shadow: 0 0 5px #f38ba8; } 
        #input-container { display: flex; padding: 20px; background-color: #181825; border-top: 1px solid #313244; }
        #prompt-input { flex: 1; padding: 12px; border-radius: 6px; border: 1px solid #45475a; background-color: #1e1e2e; color: #cdd6f4; font-size: 16px; outline: none; }
        #send-btn { margin-left: 10px; padding: 12px 24px; border-radius: 6px; border: none; background-color: #a6e3a1; color: #11111b; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.2s; }
        #send-btn:hover { background-color: #94e2d5; }
        #send-btn:disabled { background-color: #585b70; cursor: not-allowed; }
    </style>
</head>
<body>
    <div id="chat-container"></div>
    <div id="input-container">
        <input type="text" id="prompt-input" placeholder="Type a message (e.g., What is a diffusion model?)..." autocomplete="off" onkeypress="handleKeyPress(event)">
        <button id="send-btn" onclick="sendMessage()">Send</button>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.host}/ws`);
        const chatContainer = document.getElementById('chat-container');
        const input = document.getElementById('prompt-input');
        const sendBtn = document.getElementById('send-btn');
        let currentAiMessageDiv = null;

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            if (data.type === 'chunk') {
                if (!currentAiMessageDiv) {
                    currentAiMessageDiv = document.createElement('div');
                    currentAiMessageDiv.className = 'message ai-message diffusing'; // Add glowing class
                    chatContainer.appendChild(currentAiMessageDiv);
                }
                // Append text (safely replacing newlines with HTML line breaks)
                currentAiMessageDiv.innerHTML += data.text.replace(/\\n/g, '<br>');
                chatContainer.scrollTop = chatContainer.scrollHeight;
            } else if (data.type === 'done') {
                // Diffusion complete, remove the glowing effect
                if (currentAiMessageDiv) {
                    currentAiMessageDiv.classList.remove('diffusing');
                }
                currentAiMessageDiv = null;
                sendBtn.disabled = false;
                input.focus();
            } else if (data.type === 'error') {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'message ai-message';
                errorDiv.style.color = '#f38ba8';
                errorDiv.innerText = "Error: " + data.text;
                chatContainer.appendChild(errorDiv);
                sendBtn.disabled = false;
            }
        };

        function sendMessage() {
            const text = input.value.trim();
            if (!text) return;
            
            // Render user message
            const userDiv = document.createElement('div');
            userDiv.className = 'message user-message';
            userDiv.innerText = text;
            chatContainer.appendChild(userDiv);
            
            // Send to WebSocket server
            ws.send(text);
            input.value = '';
            sendBtn.disabled = true;
            currentAiMessageDiv = null;
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function handleKeyPress(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        }
    </script>
</body>
</html>
"""

@app.get("/")
async def get_ui():
    """Serves the frontend chat HTML UI."""
    return HTMLResponse(html_content)


# ---------------------------------------------------------
# WEBSOCKET STREAMING BACKEND
# ---------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    app_name = 'litellm_streaming_web'
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    
    # Initialize the ADK runner and session for this connection
    runner = InMemoryRunner(agent=agent.root_agent, app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
    )

    try:
        while True:
            # 1. Wait for prompt from user's browser
            prompt = await websocket.receive_text()
            
            content = types.Content(
                role='user',
                parts=[types.Part.from_text(text=prompt)],
            )

            saw_partial_text = False

            try:
                # 2. Run the agent with SSE mode enabled
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

                    # Stream intermediate partial diffusing chunks to the browser
                    if event.partial:
                        await websocket.send_json({"type": "chunk", "text": text})
                        saw_partial_text = True
                        continue

                    # If SSE somehow missed partial chunks and gives us the final string
                    if not saw_partial_text:
                        await websocket.send_json({"type": "chunk", "text": text})

                # 3. Tell the UI the diffusion for this message is finished
                await websocket.send_json({"type": "done"})

            except Exception as e:
                print(f"Agent Error: {e}")
                await websocket.send_json({"type": "error", "text": str(e)})

    except WebSocketDisconnect:
        print(f"Client {user_id} disconnected.")


if __name__ == '__main__':
    # Run the web application using Uvicorn
    print("Starting Web Server at http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)