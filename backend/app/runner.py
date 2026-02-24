from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .credentials import CredentialStore
from .schemas import StartTaskRequest, VerifierResult
from .utils import sanitize_log, utc_ts
from .verifier import Verifier


try:  # Autogen package compatibility matrix
    import autogen  # type: ignore  # noqa: F401
except Exception:  # noqa: BLE001
    try:
        import pyautogen as autogen  # type: ignore  # noqa: F401
    except Exception:  # noqa: BLE001
        autogen = None


@dataclass
class TaskRunner:
    task_id: str
    req: StartTaskRequest
    credential_store: CredentialStore
    push_event: Callable[[str, dict[str, Any]], None]
    verifier: Verifier
    stop_event: threading.Event = field(default_factory=threading.Event)
    state: str = "INIT"
    provided_credentials: dict[str, str] = field(default_factory=dict)

    def start(self) -> None:
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(self) -> None:
        self.state = "RUNNING"
        self.push_event("info", {"msg": "Task started", "ts": utc_ts()})

        # Fallback simulated conversation (compatible without AutoGen runtime)
        scripted_messages = [
            {
                "sender": "Planner",
                "recipient": "Researcher",
                "content": f"Task breakdown for: {self.req.task}",
            },
            {
                "sender": "Researcher",
                "recipient": "Planner",
                "content": "I may need private GitHub examples. request_credential:github:access private repos to fetch examples",
            },
            {
                "sender": "Writer",
                "recipient": "User",
                "content": "Done. Here are 3 trusted public sources about API rate limiting.",
            },
        ]

        for message in scripted_messages:
            if self.stop_event.is_set():
                self.state = "STOPPED"
                self.push_event("info", {"msg": "Task stopped by user", "ts": utc_ts()})
                self.push_event("finished", {"msg": "Stopped", "ts": utc_ts()})
                return

            self.push_event(
                "agent_message",
                {
                    "sender": message["sender"],
                    "recipient": message["recipient"],
                    "content": sanitize_log(message["content"]),
                    "ts": utc_ts(),
                },
            )

            verdict = self.verifier.verify(
                task=self.req.task,
                sender=message["sender"],
                recipient=message["recipient"],
                agent_message=message["content"],
            )
            self.push_event("verifier_result", {**verdict.model_dump(), "ts": utc_ts()})
            self._apply_actions(verdict)

        self.state = "FINISHED"
        self.push_event("finished", {"msg": "Task completed", "ts": utc_ts()})

    def _apply_actions(self, verdict: VerifierResult) -> None:
        actions = verdict.suggested_actions or []
        for action in actions:
            if action.startswith("request_credential:"):
                _, provider, reason = action.split(":", 2)
                self._handle_credential_request(provider=provider.strip(), reason=reason.strip())
                continue

            detail = f"Action processed: {action}"
            self.push_event("action_result", {"action": action.split(":", 1)[0], "detail": detail, "ts": utc_ts()})

    def _handle_credential_request(self, provider: str, reason: str) -> None:
        request_id = str(uuid.uuid4())
        self.state = f"WAITING_FOR_CREDENTIAL:{request_id}"
        payload = {
            "provider": provider,
            "description": reason,
            "scope": "",
            "request_id": request_id,
            "user_id": self.req.user_id,
            "sensitivity": "high",
            "ts": utc_ts(),
            "type": "credential_request",
        }
        self.push_event("credential_request", payload)
        self.push_event("info", {"msg": f"Execution paused waiting credential for {provider}", "ts": utc_ts()})
        value = self.credential_store.wait_for(self.req.user_id, provider, timeout=60 * 60 * 24)
        if not value:
            self.push_event("error", {"msg": f"Timeout waiting credential for {provider}", "ts": utc_ts()})
            return
        self.provided_credentials[provider] = value
        self.state = "RUNNING"
        self.push_event("info", {"msg": f"Credential for {provider} received. Resuming execution.", "ts": utc_ts()})
        self.push_event(
            "action_result",
            {
                "action": "request_credential",
                "detail": f"Credential provided for {provider}",
                "ts": utc_ts(),
            },
        )


class RunnerRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runners: dict[str, TaskRunner] = {}
        self._events: dict[str, "queue.Queue[dict[str, Any]]"] = {}

    def create(self, req: StartTaskRequest, credential_store: CredentialStore, verifier: Verifier) -> TaskRunner:
        task_id = str(uuid.uuid4())
        q: "queue.Queue[dict[str, Any]]" = queue.Queue()

        def push_event(kind: str, payload: dict[str, Any]) -> None:
            q.put({"kind": kind, "payload": payload})

        runner = TaskRunner(task_id=task_id, req=req, credential_store=credential_store, push_event=push_event, verifier=verifier)
        with self._lock:
            self._runners[task_id] = runner
            self._events[task_id] = q
        return runner

    def get_runner(self, task_id: str) -> TaskRunner | None:
        with self._lock:
            return self._runners.get(task_id)

    def get_queue(self, task_id: str) -> "queue.Queue[dict[str, Any]] | None":
        with self._lock:
            return self._events.get(task_id)
