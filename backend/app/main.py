from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .auth import create_token
from .credentials import CredentialStore
from .runner import RunnerRegistry
from .schemas import (
    CredentialListResponse,
    CredentialMetadata,
    CredentialSetRequest,
    CredentialSetResponse,
    LoginRequest,
    LoginResponse,
    StartTaskRequest,
    StartTaskResponse,
)
from .verifier import Verifier

load_dotenv()

app = FastAPI(title="Multi-Agent Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

credential_store = CredentialStore()
registry = RunnerRegistry()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/start-task", response_model=StartTaskResponse)
def start_task(req: StartTaskRequest) -> StartTaskResponse:
    verifier = Verifier(model=req.model, api_key=req.openrouter_api_key)
    runner = registry.create(req, credential_store=credential_store, verifier=verifier)
    runner.start()
    return StartTaskResponse(task_id=runner.task_id, ws=f"/ws/{runner.task_id}")


@app.post("/credentials", response_model=CredentialSetResponse)
def set_credentials(req: CredentialSetRequest) -> CredentialSetResponse:
    credential_store.set(req.user_id, req.provider, req.value)
    return CredentialSetResponse(status="ok")


@app.get("/credentials/{user_id}", response_model=CredentialListResponse)
def list_credentials(user_id: str) -> CredentialListResponse:
    providers = [CredentialMetadata(provider=p) for p in credential_store.list_providers(user_id)]
    return CredentialListResponse(user_id=user_id, providers=providers)


@app.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    token = create_token(req.user_id)
    return LoginResponse(access_token=token)


@app.websocket("/ws/{task_id}")
async def task_ws(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    q = registry.get_queue(task_id)
    runner = registry.get_runner(task_id)
    if not q or not runner:
        await websocket.send_json({"kind": "error", "payload": {"msg": "task not found"}})
        await websocket.close(code=1008)
        return

    try:
        while True:
            while not q.empty():
                event = q.get_nowait()
                await websocket.send_json(event)

            try:
                data = await websocket.receive_text()
                message: dict[str, Any] = json.loads(data)
                cmd = message.get("cmd")
                if cmd == "stop":
                    runner.stop()
                elif cmd == "credential_provided":
                    # Optional command; POST /credentials is canonical and wakes waiters.
                    pass
            except WebSocketDisconnect:
                break
            except Exception:
                await websocket.send_json({"kind": "error", "payload": {"msg": "invalid websocket command"}})
    finally:
        if runner.state not in {"FINISHED", "STOPPED"}:
            runner.stop()
