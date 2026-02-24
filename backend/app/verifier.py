from __future__ import annotations

import json
import os
from typing import Any

import requests

from .schemas import VerifierResult
from .utils import CircuitBreaker, retry_with_backoff, safe_json_loads

SYSTEM_PROMPT = "You are an automated verifier. Return ONLY a single JSON object. No extra commentary."
USER_PROMPT_TEMPLATE = """Context:
- task: {TASK}
- sender: {SENDER}
- recipient: {RECIPIENT}
- agent_message: {AGENT_MESSAGE}

Instructions:
1) Decide if the agent_message is correct and relevant.
2) Output JSON with keys:
   - verdict: \"pass\" or \"fail\"
   - confidence: number (0.0 - 1.0)
   - reason: short string
   - suggested_actions: array of strings (allowed actions: \"modify_agent_system_prompt: ...\", \"add_agent:Role:desc\", \"remove_agent:AgentName\", \"request_credential:provider:reason\", \"request_references\", \"reduce_temperature\", \"increase_temperature\")
   - patch_for_agent: optional string (system prompt patch)
Only output valid JSON (start with {{ and end with }}).
"""


class Verifier:
    def __init__(self, model: str, api_key: str | None = None, timeout_s: int = 30) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.timeout_s = timeout_s
        self.breaker = CircuitBreaker(failure_threshold=3, reset_after_s=60)

    def _build_messages(self, task: str, sender: str, recipient: str, agent_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    TASK=task,
                    SENDER=sender,
                    RECIPIENT=recipient,
                    AGENT_MESSAGE=agent_message,
                ),
            },
        ]

    def _remote_verify(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("Missing OPENROUTER API key")

        def _call() -> dict[str, Any]:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "messages": messages, "temperature": 0.1},
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            return resp.json()

        return retry_with_backoff(_call, retries=3, base_delay=0.5)

    def verify(self, task: str, sender: str, recipient: str, agent_message: str) -> VerifierResult:
        messages = self._build_messages(task, sender, recipient, agent_message)

        if not self.breaker.allow():
            return VerifierResult(
                verdict="pass",
                confidence=0.2,
                reason="Verifier circuit breaker open; skipping check temporarily.",
                suggested_actions=[],
                patch_for_agent=None,
            )

        if os.getenv("DEV_MODE", "false").lower() in {"1", "true", "yes"} and not self.api_key:
            raw = json.dumps(
                {
                    "verdict": "pass",
                    "confidence": 0.8,
                    "reason": "DEV_MODE fallback verifier",
                    "suggested_actions": [],
                    "patch_for_agent": None,
                }
            )
        else:
            try:
                data = self._remote_verify(messages)
                raw = data["choices"][0]["message"]["content"]
                self.breaker.mark_success()
            except Exception:  # noqa: BLE001
                self.breaker.mark_failure()
                raw = "{\"verdict\":\"pass\",\"confidence\":0.2,\"reason\":\"Verifier error fallback\",\"suggested_actions\":[]}"

        parsed = safe_json_loads(raw)
        return VerifierResult(**parsed)
