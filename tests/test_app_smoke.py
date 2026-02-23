from app import OPENROUTER_BASE_URL, build_llm_config, make_verifier_prompt


def test_build_llm_config_structure():
    cfg = build_llm_config(api_key="abc", model="openrouter/openai/gpt-4o-mini")
    assert "config_list" in cfg
    assert cfg["config_list"][0]["base_url"] == OPENROUTER_BASE_URL
    assert cfg["config_list"][0]["api_key"] == "abc"


def test_make_verifier_prompt_returns_messages():
    prompt = make_verifier_prompt("task", "sender", "recipient", "message")
    assert len(prompt) == 2
    assert prompt[0]["role"] == "system"
    assert "Only output valid JSON" in prompt[1]["content"]
