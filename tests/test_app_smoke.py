from app import OPENROUTER_BASE_URL, KeyVault, build_llm_config, extract_key_requests, make_verifier_prompt


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


def test_extract_key_requests_parses_markers():
    msg = "Para continuar, REQUEST_API_KEY: serpapi e NEED_API_KEY: github"
    keys = extract_key_requests(msg)
    assert "serpapi" in keys
    assert "github" in keys


def test_key_vault_request_wait_and_set():
    vault = KeyVault()
    vault.request_key("serpapi")
    assert "serpapi" in vault.requested_keys()
    vault.set_key("serpapi", "secret")
    assert vault.wait_for_key("serpapi", timeout=1)
    assert vault.get_key("serpapi") == "secret"
