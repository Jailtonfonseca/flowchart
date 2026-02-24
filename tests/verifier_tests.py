from backend.app.verifier import Verifier


def test_verifier_prompt_parsing(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    v = Verifier(model="openai/gpt-4o-mini", api_key="dummy")

    def fake_remote(messages):
        return {
            "choices": [
                {
                    "message": {
                        "content": "extra text\n{\"verdict\":\"fail\",\"confidence\":0.7,\"reason\":\"bad\",\"suggested_actions\":[\"request_references\"],\"patch_for_agent\":null}\nthanks"
                    }
                }
            ]
        }

    v._remote_verify = fake_remote
    result = v.verify("task", "a", "b", "msg")
    assert result.verdict == "fail"
    assert result.suggested_actions == ["request_references"]
