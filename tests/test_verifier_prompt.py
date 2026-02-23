import json
from unittest.mock import MagicMock
from app import Verifier, VERIFIER_SYSTEM_PROMPT

def test_verifier_make_prompt():
    v = Verifier(api_key="dummy", model="dummy")
    prompt = v._make_prompt("task1", "sender1", "recipient1", "message1")

    assert len(prompt) == 2
    assert prompt[0]["role"] == "system"
    assert prompt[0]["content"] == VERIFIER_SYSTEM_PROMPT
    assert "task1" in prompt[1]["content"]
    assert "sender1" in prompt[1]["content"]

def test_verifier_json_parsing_valid():
    v = Verifier(api_key="dummy", model="dummy")
    json_str = '{"verdict": "pass", "confidence": 0.9, "reason": "ok", "suggested_actions": []}'
    result = v._parse_json(json_str)
    assert result["verdict"] == "pass"
    assert result["confidence"] == 0.9

def test_verifier_json_parsing_markdown():
    v = Verifier(api_key="dummy", model="dummy")
    json_str = '```json\n{"verdict": "fail", "confidence": 0.1}\n```'
    result = v._parse_json(json_str)
    assert result["verdict"] == "fail"

def test_verifier_json_parsing_broken():
    v = Verifier(api_key="dummy", model="dummy")
    json_str = 'This is not json but mentions fail.'
    result = v._parse_json(json_str)
    assert result["verdict"] == "fail" # Heuristic
