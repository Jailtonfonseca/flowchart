from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class StartTaskRequest(BaseModel):
    task: str
    model: str = "openai/gpt-4o-mini"
    openrouter_api_key: Optional[str] = None
    max_agents: int = Field(default=3, ge=1, le=12)
    auto_apply: bool = True
    user_id: str


class StartTaskResponse(BaseModel):
    task_id: str
    ws: str


class CredentialSetRequest(BaseModel):
    user_id: str
    provider: str
    value: str


class CredentialSetResponse(BaseModel):
    status: Literal["ok"] = "ok"


class CredentialMetadata(BaseModel):
    provider: str


class CredentialListResponse(BaseModel):
    user_id: str
    providers: List[CredentialMetadata]


class LoginRequest(BaseModel):
    user_id: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class VerifierResult(BaseModel):
    verdict: Literal["pass", "fail"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    suggested_actions: List[str] = Field(default_factory=list)
    patch_for_agent: Optional[str] = None


class WsEvent(BaseModel):
    kind: str
    payload: dict
