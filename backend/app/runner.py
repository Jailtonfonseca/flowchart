import threading
import json
import time
import uuid
import logging
import re
from typing import List, Dict, Callable, Any, Optional

try:
    import autogen
except ImportError:
    autogen = None

from app.schemas import (
    TaskRequest, AgentMessagePayload, VerifierResultPayload,
    CredentialRequestPayload, ActionResultPayload
)
from app.verifier import Verifier
from app.credentials import credential_store
from app.utils import safe_log

logger = logging.getLogger("app.runner")

class TaskRunner:
    def __init__(self, task_request: TaskRequest, event_callback: Callable[[Dict[str, Any]], None], task_id: Optional[str] = None):
        self.task_request = task_request
        self.event_callback = event_callback
        self.task_id = task_id or str(uuid.uuid4())
        self.stop_event = threading.Event()
        self.verifier = Verifier(api_key=task_request.openrouter_api_key)
        self.agents: List[Any] = []
        self.manager = None

    def start(self) -> str:
        """Starts the task in a background thread."""
        if autogen is None:
            self._push_event("error", {"msg": "AutoGen library not found. Please install pyautogen."})
            return self.task_id

        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return self.task_id

    def stop(self):
        self.stop_event.set()

    def _push_event(self, kind: str, payload: Any):
        """Helper to send events to frontend."""
        if hasattr(payload, "dict"):
            payload = payload.dict()

        event = {
            "kind": kind,
            "payload": payload
        }
        self.event_callback(event)

    def _run(self):
        """Main execution loop."""
        try:
            self._push_event("info", {"msg": f"Starting task: {self.task_request.task}", "ts": int(time.time())})

            # 1. Build Agents
            self.agents = self._build_agents()
            if not self.agents:
                self._push_event("error", {"msg": "Failed to build agents.", "ts": int(time.time())})
                return

            # 2. Setup GroupChat
            groupchat = autogen.GroupChat(
                agents=self.agents,
                messages=[],
                max_round=20,
                speaker_selection_method="auto"
            )

            self.manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=self._get_llm_config())

            # 3. Register Hooks (to capture messages)
            for agent in self.agents:
                agent.register_reply(
                    [autogen.Agent, None],
                    self._reply_interceptor,
                    position=0
                )

            # 4. Start Chat
            user_proxy = self.agents[0]

            self.manager.initiate_chat(
                user_proxy,
                message=self.task_request.task
            )

            self._push_event("finished", {"msg": "Task completed.", "ts": int(time.time())})

        except Exception as e:
            logger.exception("Error in runner")
            self._push_event("error", {"msg": str(e), "ts": int(time.time())})

    def _reply_interceptor(self, recipient, messages, sender, config):
        """
        Intercepts messages to:
        1. Send to UI
        2. Run Verifier
        3. Apply Actions (which might block for credentials)
        """
        if self.stop_event.is_set():
            return True, "Execution stopped by user."

        # Extract latest message
        if isinstance(messages, list):
            content = messages[-1].get("content")
        else:
            content = messages

        if not content:
            return False, None

        # 1. Emit to UI
        ts = int(time.time())
        self._push_event("agent_message", AgentMessagePayload(
            sender=sender.name,
            recipient=recipient.name,
            content=str(content),
            ts=ts
        ))

        # 2. Run Verifier
        # Skip verification for system messages or simple ACKs
        if sender.name == "System" or "VERIFIER_PATCH" in str(content):
            return False, None

        verifier_result = self.verifier.verify(
            task=self.task_request.task,
            sender=sender.name,
            recipient=recipient.name,
            message=str(content)
        )
        verifier_result.ts = int(time.time())

        self._push_event("verifier_result", verifier_result)

        # 3. Apply Actions
        if verifier_result.verdict == "fail":
            if self.task_request.auto_apply:
                self._apply_actions(verifier_result.suggested_actions, verifier_result.patch_for_agent)
            else:
                # In non-auto-apply, we just show the user.
                # But if there is a credential request, we might want to force it?
                pass

        # Check for credential requests specifically in suggestions
        for action in verifier_result.suggested_actions:
            if action.startswith("request_credential:"):
                self._handle_credential_request_action(action)

        return False, None

    def _apply_actions(self, actions: List[str], patch: Optional[str]):
        """Executes actions suggested by Verifier."""
        for action in actions:
            try:
                if action.startswith("add_agent:"):
                    parts = action.split(":", 2)
                    if len(parts) == 3:
                        self._add_agent(parts[1], parts[2])
                elif action.startswith("remove_agent:"):
                    name = action.split(":")[1]
                    self._remove_agent(name)
                elif action.startswith("request_credential:"):
                     self._handle_credential_request_action(action)
                elif action == "request_references":
                     self._inject_system_message("Please provide references for the previous claim.")

            except Exception as e:
                logger.error(f"Failed to apply action {action}: {e}")

        if patch:
            self._inject_system_message(f"VERIFIER_PATCH: {patch}")

    def _handle_credential_request_action(self, action: str):
        """
        Parses request_credential:provider:reason
        Pauses execution using CredentialStore.wait_for
        """
        parts = action.split(":", 2)
        if len(parts) < 3:
            return

        provider = parts[1]
        reason = parts[2]
        user_id = self.task_request.user_id

        if credential_store.has(user_id, provider):
            return

        # 1. Notify UI
        request_id = str(uuid.uuid4())
        ts = int(time.time())
        self._push_event("credential_request", CredentialRequestPayload(
            request_id=request_id,
            provider=provider,
            description=reason,
            user_id=user_id,
            ts=ts
        ))

        # 2. Block until provided
        self._push_event("info", {"msg": f"Paused waiting for credential: {provider}", "ts": ts})

        val = credential_store.wait_for(user_id, provider, timeout=86400)

        if val:
            self._push_event("info", {"msg": f"Credential {provider} received. Resuming.", "ts": int(time.time())})
            self._push_event("action_result", ActionResultPayload(
                action="credential_provided",
                detail=f"Credential for {provider} was provided.",
                ts=int(time.time())
            ))
            # Inject notification
            self._inject_system_message(f"SYSTEM: The credential for {provider} has been provided and is available in the environment.")
        else:
            self._push_event("error", {"msg": f"Timed out waiting for {provider}", "ts": int(time.time())})
            self.stop()

    def _inject_system_message(self, content: str):
        if self.manager and hasattr(self.manager, "groupchat"):
             # We append to the groupchat messages directly.
             # This is a bit of a hack, but AutoGen supports it if the next agent reads history.
             self.manager.groupchat.messages.append({
                 "role": "system",
                 "content": content,
                 "name": "System"
             })

    def _add_agent(self, role: str, desc: str):
        if not self.manager:
            return

        # Check if exists
        if any(a.name == role for a in self.manager.groupchat.agents):
            return

        logger.info(f"Adding agent {role}")
        new_agent = autogen.AssistantAgent(
            name=role,
            system_message=desc,
            llm_config=self._get_llm_config()
        )
        new_agent.register_reply([autogen.Agent, None], self._reply_interceptor, position=0)

        self.manager.groupchat.agents.append(new_agent)
        self._push_event("action_result", ActionResultPayload(
            action="add_agent",
            detail=f"Added agent {role}",
            ts=int(time.time())
        ))

    def _remove_agent(self, name: str):
        if not self.manager:
            return

        agents = self.manager.groupchat.agents
        target = next((a for a in agents if a.name == name), None)
        if target:
            agents.remove(target)
            self._push_event("action_result", ActionResultPayload(
                action="remove_agent",
                detail=f"Removed agent {name}",
                ts=int(time.time())
            ))

    def _build_agents(self) -> List[Any]:
        """
        Simulates an AgentBuilder.
        """
        llm_config = self._get_llm_config()

        user_proxy = autogen.UserProxyAgent(
            name="UserProxy",
            human_input_mode="NEVER",
            code_execution_config={"work_dir": "coding", "use_docker": False},
            max_consecutive_auto_reply=10
        )

        primary_assistant = autogen.AssistantAgent(
            name="PrimaryAssistant",
            system_message="You are a helpful AI assistant. Solve the user's task.",
            llm_config=llm_config
        )

        return [user_proxy, primary_assistant]

    def _get_llm_config(self):
        config_list = []
        if self.task_request.openrouter_api_key:
             config_list.append({
                 "model": self.task_request.model,
                 "api_key": self.task_request.openrouter_api_key,
                 "base_url": "https://openrouter.ai/api/v1"
             })
        else:
            config_list.append({
                "model": "gpt-4",
                "api_key": "sk-mock-key"
            })

        return {
            "config_list": config_list,
            "temperature": 0.7,
            "timeout": 30,
            "cache_seed": None # Disable caching for POC to ensure requests go out
        }
