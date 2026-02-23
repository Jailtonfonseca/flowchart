import json

from app import make_verifier_prompt, parse_verifier_json


def test_make_verifier_prompt_contains_context_and_instructions():
    messages = make_verifier_prompt(
        task="Resumir texto",
        sender="agent-1",
        recipient="manager",
        agent_message="Aqui está o resumo.",
    )
    assert messages[0]["role"] == "system"
    assert "automated verifier" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "agent_message" in messages[1]["content"]


def test_parse_verifier_json_extracts_required_fields():
    raw = json.dumps(
        {
            "verdict": "fail",
            "confidence": 0.83,
            "reason": "Sem fontes",
            "suggested_actions": ["request_references", "reduce_temperature"],
        }
    )
    parsed = parse_verifier_json(raw)
    assert parsed["verdict"] == "fail"
    assert parsed["confidence"] == 0.83
    assert "request_references" in parsed["suggested_actions"]
