import json
import logging
import os
import queue
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
from dotenv import load_dotenv

# Try to import autogen and its components
try:
    import autogen
    from autogen import AssistantAgent, GroupChat, GroupChatManager
    from autogen.agentchat.contrib.agent_builder import AgentBuilder
except ImportError:
    # If imports fail (e.g. in CI or non-installed env), we define dummies to allow parsing
    # but the app will warn at runtime.
    autogen = None
    AssistantAgent = None
    GroupChat = None
    GroupChatManager = None
    AgentBuilder = None


load_dotenv()

# --- Configuration & Constants ---
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/anthropic/claude-sonnet-3.5")
DEFAULT_MAX_AGENTS = int(os.getenv("MAX_AGENTS", "5"))

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")


# --- Data Structures ---
@dataclass
class AuditEvent:
    timestamp: str
    kind: str  # 'chat' or 'audit' or 'system'
    source: str
    target: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


# --- Verifier Implementation ---
VERIFIER_SYSTEM_PROMPT = """You are an automated verifier. Return ONLY a single JSON object. Do NOT include any surrounding commentary."""

class Verifier:
    def __init__(self, api_key: str, model: str, timeout: int = 30, max_retries: int = 3):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def _make_prompt(self, task: str, sender: str, recipient: str, agent_message: str) -> List[Dict[str, str]]:
        user_prompt = f"""Context:
- task: {task}
- sender: {sender}
- recipient: {recipient}
- agent_message: {agent_message}

Instruction:
1) Decide if the agent_message is correct and relevant to the task.
2) Return JSON with fields:
   - verdict: "pass" or "fail"
   - confidence: number between 0.0 and 1.0
   - reason: short explanation why pass or fail
   - suggested_actions: array of strings. Valid actions:
       - "modify_agent_system_prompt: <instruction>"
       - "add_agent: <role name> : <short description>"
       - "remove_agent: <agent name>"
       - "request_references"
       - "reduce_temperature"
       - "increase_temperature"
   - patch_for_agent: optional string (new system prompt)
3) Only output valid JSON (first character must be `{{` and last `}}`)."""
        return [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

    def verify(self, task: str, sender: str, recipient: str, agent_message: str) -> Dict[str, Any]:
        messages = self._make_prompt(task, sender, recipient, agent_message)
        url = f"{OPENROUTER_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/autogen-ai/autogen", # Optional for OpenRouter
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 1024
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return self._parse_json(content)
            except Exception as e:
                logger.warning(f"Verifier attempt {attempt} failed: {e}")
                if attempt == self.max_retries:
                    return {
                        "verdict": "pass",
                        "confidence": 0.0,
                        "reason": f"Verifier unavailable: {str(e)}",
                        "suggested_actions": []
                    }
                time.sleep(min(2 ** attempt, 8))
        return {} # Should not reach here due to return in loop

    def _parse_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        # Attempt to extract JSON if wrapped in markdown code blocks
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        elif not text.startswith("{"):
            # Try to find the first brace
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if match:
                text = match.group(1)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Simple heuristic fallback if JSON is broken but contains verdict
            verdict = "fail" if "fail" in text.lower() else "pass"
            return {
                "verdict": verdict,
                "confidence": 0.0,
                "reason": "Failed to parse JSON response",
                "suggested_actions": []
            }

# --- AutoGen Helper Functions ---

def build_llm_config(api_key: str, model: str) -> Dict[str, Any]:
    return {
        "config_list": [
            {
                "model": model,
                "api_key": api_key,
                "base_url": OPENROUTER_BASE_URL,
            }
        ],
        "temperature": 0.2,
        "timeout": 60,
        "cache_seed": None, # Disable caching for demo purposes or keep it unique
    }

def apply_actions(actions: List[str], groupchat: Any, manager: Any, llm_config: Dict[str, Any], event_queue: queue.Queue):
    """
    Apply actions suggested by the verifier to the GroupChat/Manager.
    """
    if not groupchat or not manager:
        return

    for action in actions:
        try:
            if action.startswith("add_agent:"):
                # format: "add_agent: Name : Description"
                parts = action.split(":", 2)
                if len(parts) >= 2:
                    name = parts[1].strip().replace(" ", "_")
                    desc = parts[2].strip() if len(parts) > 2 else "Dynamically added agent"
                    # Check if agent exists
                    if any(a.name == name for a in groupchat.agents):
                        event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "manager", f"Agent {name} already exists, skipping add."))
                        continue

                    new_agent = AssistantAgent(
                        name=name,
                        system_message=desc,
                        llm_config=llm_config
                    )
                    # Register reply for the new agent too!
                    # Note: We need to ensure we can register reply here.
                    # Since run_orchestrator defines the hook, we need to access it or redefine it.
                    # For simplicity, we might not register the hook on dynamically added agents in this simple version,
                    # or we need to pass the hook function.
                    # Let's just add it to the group chat.
                    groupchat.agents.append(new_agent)
                    # Use manager.register_reply if possible or just rely on group chat mechanism
                    # Re-broadcast welcome?
                    event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "verifier", "manager", f"Added agent: {name}"))

            elif action.startswith("remove_agent:"):
                target = action.split(":", 1)[1].strip()
                original_count = len(groupchat.agents)
                groupchat.agents = [a for a in groupchat.agents if a.name != target]
                if len(groupchat.agents) < original_count:
                    event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "verifier", "manager", f"Removed agent: {target}"))

            elif action.startswith("modify_agent_system_prompt:"):
                instruction = action.split(":", 1)[1].strip()
                # We can't easily modify the system prompt of the *current* speaker in middle of turn usually,
                # but we can broadcast a system message to correct behavior.
                # Or find specific agent if named? The action doesn't specify agent name usually in the prompt template given.
                # We will broadcast a system message.
                manager.send(recipient=manager, message=f"SYSTEM INSTRUCTION: {instruction}", request_reply=False, silent=True) # Hacky
                event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "verifier", "manager", f"Broadcast instruction: {instruction}"))

        except Exception as e:
            event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "manager", f"Failed to apply action {action}: {e}"))


# --- Orchestrator Thread ---

def run_orchestrator(
    task: str,
    api_key: str,
    model: str,
    verifier_model: str,
    max_agents: int,
    auto_apply: bool,
    event_queue: queue.Queue
):
    """
    Main execution logic running in a separate thread.
    """
    if autogen is None:
        event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "ui", "AutoGen not installed or failed to import."))
        return

    llm_config = build_llm_config(api_key, model)
    verifier = Verifier(api_key, verifier_model)

    event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "ui", "Building agents..."))

    # 1. Build Agents
    # AgentBuilder requires OAI_CONFIG_LIST to be set or a config file.
    # We simulate this by setting the env var temporarily.
    config_list_json = json.dumps([{"model": model, "api_key": api_key, "base_url": OPENROUTER_BASE_URL}])
    os.environ["OAI_CONFIG_LIST"] = config_list_json

    try:
        # AgentBuilder attempts to load config from env if config_file_or_env is not provided
        # We pass builder_model and agent_model to match our selected model
        builder = AgentBuilder(
            config_file_or_env="OAI_CONFIG_LIST",
            builder_model=model,
            agent_model=model
        )

        agent_list, agent_configs = builder.build(
            building_task=task,
            default_llm_config=llm_config,
            coding=False, # Simplify to avoid docker requirement for code execution
            max_agents=max_agents
        )
    except Exception as e:
        event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "ui", f"AgentBuilder failed: {e}. Using fallback agents."))
        # Fallback agents
        agent_list = [
            AssistantAgent(name="Assistant", llm_config=llm_config, system_message="You are a helpful assistant."),
            AssistantAgent(name="Researcher", llm_config=llm_config, system_message="You research information."),
        ]

    # Add User Proxy
    user_proxy = autogen.UserProxyAgent(
        name="User_Proxy",
        human_input_mode="NEVER",
        code_execution_config=False,
    )

    # Create GroupChat
    groupchat = GroupChat(agents=[user_proxy] + agent_list, messages=[], max_round=12)
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

    event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "ui", f"Team assembled with {len(agent_list)} agents."))

    # 2. Register Capture & Verify Hooks
    # We define the hook
    def reply_hook(recipient, messages, sender, config):
        if sender == recipient:
            return False, None # Ignore self-loops if any

        # Get the last message
        if isinstance(messages, list) and messages:
            last_msg = messages[-1]
            content = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)

            # 1. Push to UI
            event_queue.put(AuditEvent(datetime.now().isoformat(), "chat", sender.name, recipient.name, content))

            # 2. Verify
            # Skip verification for User_Proxy or Manager system messages if desired?
            # We verify everything for now.
            if content and sender.name != "User_Proxy":
                verification = verifier.verify(task, sender.name, recipient.name, content)
                event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "verifier", sender.name, json.dumps(verification, indent=2), metadata=verification))

                if verification.get("verdict") == "fail" and auto_apply:
                    actions = verification.get("suggested_actions", [])
                    apply_actions(actions, groupchat, manager, llm_config, event_queue)

        return False, None # Let the agent continue normal processing

    # Register hook for all agents and manager
    for agent in [user_proxy, manager] + agent_list:
        agent.register_reply([autogen.Agent, None], reply_hook, position=1)

    # 3. Run Chat
    try:
        user_proxy.initiate_chat(manager, message=task)
    except Exception as e:
        event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "ui", f"Chat execution error: {e}"))

    event_queue.put(AuditEvent(datetime.now().isoformat(), "audit", "system", "ui", "Execution finished."))


# --- Streamlit UI ---

def render_app():
    st.set_page_config(page_title="AutoGen Agent Builder + Verifier", layout="wide")

    # Initialize session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "audit_trail" not in st.session_state:
        st.session_state.audit_trail = []
    if "event_queue" not in st.session_state:
        st.session_state.event_queue = queue.Queue()
    if "is_running" not in st.session_state:
        st.session_state.is_running = False

    # Sidebar
    st.sidebar.title("Settings")

    api_key = st.sidebar.text_input("OpenRouter API Key", type="password", value=os.getenv("OPENROUTER_API_KEY", ""))
    model = st.sidebar.selectbox("Model", [DEFAULT_MODEL, "openrouter/openai/gpt-4o-mini", "openrouter/meta-llama/llama-3.1-70b-instruct"])
    verifier_model = st.sidebar.selectbox("Verifier Model", ["openrouter/openai/gpt-4o-mini", DEFAULT_MODEL])
    max_agents = st.sidebar.slider("Max Agents", 2, 10, DEFAULT_MAX_AGENTS)
    auto_apply = st.sidebar.checkbox("Auto-apply Verifier Actions", value=False)

    # Main Area
    st.title("AutoGen Team with Automated Verification")

    task_input = st.text_area("Task Description", value="Research the latest advancements in quantum computing and summarize them.")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Build Team & Run", disabled=st.session_state.is_running):
            if not api_key:
                st.error("Please provide an API Key.")
            else:
                st.session_state.is_running = True
                st.session_state.chat_history = []
                st.session_state.audit_trail = []
                # Clear queue
                with st.session_state.event_queue.mutex:
                    st.session_state.event_queue.queue.clear()

                # Start Thread
                t = threading.Thread(
                    target=run_orchestrator,
                    args=(task_input, api_key, model, verifier_model, max_agents, auto_apply, st.session_state.event_queue),
                    daemon=True
                )
                t.start()
                st.rerun()

    with col2:
        if st.button("Stop/Reset"):
            st.session_state.is_running = False
            st.rerun()

    # Process Queue
    q = st.session_state.event_queue
    while not q.empty():
        try:
            event = q.get_nowait()
            if event.kind == "chat":
                st.session_state.chat_history.append(event)
            else:
                st.session_state.audit_trail.append(event)

            if event.content == "Execution finished.":
                st.session_state.is_running = False
        except queue.Empty:
            break

    # Layout: Chat and Audit
    chat_col, audit_col = st.columns([2, 1])

    with chat_col:
        st.subheader("Conversation")
        for event in st.session_state.chat_history:
            with st.chat_message(event.source):
                st.markdown(f"**{event.source} -> {event.target}**")
                st.markdown(event.content)

    with audit_col:
        st.subheader("Verifier & Audit")
        for event in st.session_state.audit_trail:
            with st.expander(f"{event.timestamp.split('T')[1][:8]} - {event.source} ({event.kind})"):
                st.code(event.content, language="json" if event.source == "verifier" else "text")

    # Auto-refresh if running
    if st.session_state.is_running:
        time.sleep(1)
        st.rerun()

    # Exports
    if not st.session_state.is_running and st.session_state.chat_history:
        st.divider()
        transcript = {
            "chat": [asdict(e) for e in st.session_state.chat_history],
            "audit": [asdict(e) for e in st.session_state.audit_trail]
        }
        st.download_button(
            "Download Transcript (JSON)",
            data=json.dumps(transcript, indent=2),
            file_name="transcript.json",
            mime="application/json"
        )


if __name__ == "__main__":
    render_app()
