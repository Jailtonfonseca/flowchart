from typing import List, Optional, Any
from pydantic import BaseModel, Field

# --- Request Models ---
class TaskRequest(BaseModel):
    task: str
    model: str = "gpt-4"
    openrouter_api_key: Optional[str] = None
    max_agents: int = 5
    auto_apply: bool = False
    user_id: str

class TaskResponse(BaseModel):
    task_id: str
    ws: str

class CredentialRequest(BaseModel):
    user_id: str
    provider: str
    value: str

class CredentialInfo(BaseModel):
    provider: str
    user_id: str

# --- WebSocket Payloads ---
# These are helper models for constructing payloads.
# The actual payload sent via WS will be wrapped in {"kind": ..., "payload": ...}

class AgentMessagePayload(BaseModel):
    sender: str
    recipient: str
    content: str
    ts: int

class VerifierResultPayload(BaseModel):
    verdict: str  # "pass" | "fail"
    confidence: float
    reason: str
    suggested_actions: List[str]
    patch_for_agent: Optional[str] = None
    ts: int

class CredentialRequestPayload(BaseModel):
    request_id: str
    provider: str
    description: str
    scope: Optional[str] = None
    user_id: str
    sensitivity: str = "high"
    ts: int

class ActionResultPayload(BaseModel):
    action: str
    detail: str
    ts: int

class BaseEventPayload(BaseModel):
    msg: str
    ts: int
