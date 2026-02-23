import json
import logging
import requests
import re
from typing import Dict, Any, Optional
from app.schemas import VerifierResultPayload

logger = logging.getLogger("app.verifier")

class Verifier:
    def __init__(self, api_key: Optional[str] = None, model: str = "openai/gpt-3.5-turbo"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    def verify(self, task: str, sender: str, recipient: str, message: str) -> VerifierResultPayload:
        """
        Calls the Verifier LLM to check the message.
        """
        if not self.api_key:
            # Fallback mock for testing/no-key scenarios
            logger.warning("No OpenRouter API key provided. Using mock verifier (always pass).")
            return VerifierResultPayload(
                verdict="pass",
                confidence=1.0,
                reason="Mock verifier: No API key provided.",
                suggested_actions=[],
                ts=0
            )

        system_prompt = """You are an automated verifier. Return ONLY a single JSON object. No extra commentary."""

        user_prompt = f"""
Context:
- task: {task}
- sender: {sender}
- recipient: {recipient}
- agent_message: {message}

Instructions:
1) Decide if the agent_message is correct and relevant.
2) Output JSON with keys:
   - verdict: "pass" or "fail"
   - confidence: number (0.0 - 1.0)
   - reason: short string
   - suggested_actions: array of strings (allowed actions: "modify_agent_system_prompt: ...", "add_agent:Role:desc", "remove_agent:AgentName", "request_credential:provider:reason", "request_references", "reduce_temperature", "increase_temperature")
   - patch_for_agent: optional string (system prompt patch)
Only output valid JSON (start with {{ and end with }}).
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000", # OpenRouter req
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            parsed = self._parse_json(content)

            return VerifierResultPayload(
                verdict=parsed.get("verdict", "fail"),
                confidence=parsed.get("confidence", 0.0),
                reason=parsed.get("reason", "Parse error or unknown"),
                suggested_actions=parsed.get("suggested_actions", []),
                patch_for_agent=parsed.get("patch_for_agent"),
                ts=0 # Set by caller or here
            )

        except Exception as e:
            logger.error(f"Verifier LLM call failed: {e}")
            return VerifierResultPayload(
                verdict="fail",
                confidence=0.0,
                reason=f"Verifier error: {str(e)}",
                suggested_actions=[],
                ts=0
            )

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Robustly parses JSON from LLM output."""
        try:
            # First try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: try to clean markdown code blocks
        clean_text = re.sub(r"```json\n|\n```", "", text)
        clean_text = re.sub(r"```", "", clean_text)
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
             logger.error(f"Failed to parse JSON from verifier output: {text}")
             return {
                 "verdict": "fail",
                 "reason": "Invalid JSON output from Verifier",
                 "suggested_actions": []
             }
