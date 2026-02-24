import threading
import time

from backend.app.credentials import CredentialStore
from backend.app.runner import TaskRunner
from backend.app.schemas import StartTaskRequest, VerifierResult


class DummyVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, task, sender, recipient, agent_message):
        self.calls += 1
        if "request_credential" in agent_message:
            return VerifierResult(
                verdict="fail",
                confidence=0.9,
                reason="needs credential",
                suggested_actions=["request_credential:github:token required"],
                patch_for_agent=None,
            )
        return VerifierResult(
            verdict="pass",
            confidence=0.9,
            reason="ok",
            suggested_actions=[],
            patch_for_agent=None,
        )


def test_credentials_store_set_get_wait(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    store = CredentialStore()
    out = {"value": None}

    def waiter():
        out["value"] = store.wait_for("u1", "github", timeout=2)

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.1)
    store.set("u1", "github", "secret")
    t.join(timeout=2)

    assert store.has("u1", "github") is True
    assert store.get("u1", "github") == "secret"
    assert out["value"] == "secret"


def test_runner_credential_request_flow(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")
    store = CredentialStore()
    req = StartTaskRequest(
        task="test",
        model="openai/gpt-4o-mini",
        openrouter_api_key=None,
        max_agents=3,
        auto_apply=True,
        user_id="u1",
    )
    events = []

    def push(kind, payload):
        events.append({"kind": kind, "payload": payload})

    runner = TaskRunner(task_id="t1", req=req, credential_store=store, push_event=push, verifier=DummyVerifier())
    th = threading.Thread(target=runner._run)
    th.start()
    time.sleep(0.2)
    store.set("u1", "github", "gh-secret")
    th.join(timeout=5)

    kinds = [e["kind"] for e in events]
    assert "credential_request" in kinds
    assert "finished" in kinds
    assert runner.provided_credentials["github"] == "gh-secret"
