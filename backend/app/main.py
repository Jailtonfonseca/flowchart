import asyncio
import logging
import uuid
from typing import Dict, List, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.schemas import (
    TaskRequest, TaskResponse, CredentialRequest,
    CredentialInfo, CredentialRequestPayload
)
from app.credentials import credential_store
from app.runner import TaskRunner
from app.utils import safe_log

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app.main")

# Global State
tasks: Dict[str, TaskRunner] = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.message_buffer: Dict[str, List[Dict]] = {} # Simple buffer for early messages

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket

        # Flush buffer
        if task_id in self.message_buffer:
            for msg in self.message_buffer[task_id]:
                await websocket.send_json(msg)
            del self.message_buffer[task_id]

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]

    async def send_personal_message(self, message: dict, task_id: str):
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending WS message: {e}")
                self.disconnect(task_id)
        else:
            # Buffer if not connected yet (up to a limit)
            if task_id not in self.message_buffer:
                self.message_buffer[task_id] = []
            if len(self.message_buffer[task_id]) < 100:
                self.message_buffer[task_id].append(message)

manager = ConnectionManager()

app = FastAPI(title="Multi-Agent Runner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/start-task", response_model=TaskResponse)
async def start_task(request: TaskRequest):
    """
    Starts a new agent task.
    """
    task_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()

    # Callback wrapper to bridge sync Runner -> async WS
    def event_callback(event: Dict[str, Any]):
        # We need to schedule the async send on the main event loop
        try:
            if loop.is_running():
                 asyncio.run_coroutine_threadsafe(
                    manager.send_personal_message(event, task_id),
                    loop
                )
        except RuntimeError:
            pass

    runner = TaskRunner(task_request=request, event_callback=event_callback, task_id=task_id)
    tasks[task_id] = runner

    # Start the runner
    runner.start()

    return TaskResponse(task_id=task_id, ws=f"/ws/{task_id}")

@app.post("/credentials")
async def save_credential(request: CredentialRequest):
    """
    Receives a credential from the user/frontend.
    Encrypted and stored. Notifies any waiting runners.
    """
    credential_store.set(request.user_id, request.provider, request.value)
    return {"status": "ok"}

@app.get("/credentials/{user_id}", response_model=List[str])
async def list_credentials(user_id: str):
    """
    Returns list of providers for which we have credentials (metadata only).
    """
    return credential_store.list_providers(user_id)

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await manager.connect(websocket, task_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle commands from frontend (stop, approve, etc)
            if task_id in tasks:
                runner = tasks[task_id]
                cmd = data.get("cmd")
                if cmd == "stop":
                    runner.stop()
                    await manager.send_personal_message({"kind": "info", "payload": {"msg": "Stopping...", "ts": 0}}, task_id)
                elif cmd == "credential_provided":
                    pass
    except WebSocketDisconnect:
        manager.disconnect(task_id)
