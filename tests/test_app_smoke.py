import pytest
import app

def test_build_llm_config():
    config = app.build_llm_config("key123", "gpt-4")
    assert config["config_list"][0]["api_key"] == "key123"
    assert config["config_list"][0]["model"] == "gpt-4"
    assert config["timeout"] == 60

def test_verifier_init():
    v = app.Verifier("key1", "model1")
    assert v.api_key == "key1"
    assert v.model == "model1"

def test_agent_builder_logic_is_present():
    # Just check if we can call the build function (mocked) or check if logic exists
    # app.py defines `build_llm_config`
    assert hasattr(app, "build_llm_config")
    assert hasattr(app, "Verifier")
    assert hasattr(app, "run_orchestrator")
