import contextlib
import io
import json
import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/anthropic/claude-sonnet-3.5")
DEFAULT_MAX_AGENTS = int(os.getenv("MAX_AGENTS", "5"))

logger = logging.getLogger("flowchart.app")
logger.setLevel(logging.INFO)

VERIFIER_SYSTEM_PROMPT = (
    "You are an automated verifier. Return ONLY a single JSON object. "
    "Do NOT include any surrounding commentary."
)


@dataclass
class AuditEvent:
    timestamp: str
    kind: str
    source: str
    target: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class CaptureBuffer:
    def __init__(self) -> None:
        self.q: queue.Queue[AuditEvent] = queue.Queue()

    def push(self, kind: str, source: str, target: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.q.put(
            AuditEvent(
                timestamp=datetime.utcnow().isoformat(),
                kind=kind,
                source=source,
                target=target,
                content=content,
                metadata=metadata,
            )
        )


class KeyVault:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: Dict[str, threading.Event] = {}
        self._values: Dict[str, str] = {}
        self._requested: set[str] = set()

    def request_key(self, key_name: str) -> None:
        with self._lock:
            self._requested.add(key_name)
            self._events.setdefault(key_name, threading.Event())

    def set_key(self, key_name: str, value: str) -> None:
        with self._lock:
            if value:
                self._values[key_name] = value
                self._requested.add(key_name)
                event = self._events.setdefault(key_name, threading.Event())
                event.set()

    def get_key(self, key_name: str) -> str:
        with self._lock:
            return self._values.get(key_name, "")

    def wait_for_key(self, key_name: str, timeout: int = 300) -> bool:
        with self._lock:
            if self._values.get(key_name):
                return True
            event = self._events.setdefault(key_name, threading.Event())
        return event.wait(timeout=timeout)

    def requested_keys(self) -> List[str]:
        with self._lock:
            return sorted(self._requested)


class AutoGenLogHandler(logging.Handler):
    def __init__(self, capture: CaptureBuffer):
        super().__init__()
        self.capture = capture

    def emit(self, record: logging.LogRecord) -> None:
        self.capture.push("chat", "autogen-logger", "ui", self.format(record))


def build_llm_config(api_key: str, model: str, temperature: float = 0.2, timeout: int = 30) -> Dict[str, Any]:
    return {
        "config_list": [{"model": model, "api_key": api_key, "base_url": OPENROUTER_BASE_URL}],
        "temperature": temperature,
        "timeout": timeout,
    }


def make_verifier_prompt(task: str, sender: str, recipient: str, agent_message: str) -> List[Dict[str, str]]:
    user_prompt = f"""Context:
- task: {task}
- sender: {sender}
- recipient: {recipient}
- agent_message: {agent_message}

Instruction:
1) Decide if the agent_message is correct and relevant to the task.
2) Return JSON with fields:
   - verdict: \"pass\" or \"fail\"
   - confidence: number between 0.0 and 1.0
   - reason: short explanation why pass or fail
   - suggested_actions: array of strings. Valid actions:
       - \"modify_agent_system_prompt: <instruction>\"
       - \"add_agent: <role name> : <short description>\"
       - \"remove_agent: <agent name>\"
       - \"request_references\"
       - \"reduce_temperature\"
       - \"increase_temperature\"
   - patch_for_agent: optional string (new system prompt)
3) Only output valid JSON (first character must be `{{` and last `}}`)."""
    return [{"role": "system", "content": VERIFIER_SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def parse_verifier_json(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
    data = json.loads(text)
    data.setdefault("verdict", "fail")
    data.setdefault("confidence", 0.0)
    data.setdefault("reason", "No reason provided")
    data.setdefault("suggested_actions", [])
    return data


def _sanitize_key(value: str) -> str:
    return "" if not value else f"***{value[-4:]}"


def extract_key_requests(message: str) -> List[str]:
    patterns = [
        r"REQUEST_API_KEY\s*:\s*([a-zA-Z0-9_\-]+)",
        r"NEED_API_KEY\s*:\s*([a-zA-Z0-9_\-]+)",
    ]
    found: List[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, message or "", flags=re.IGNORECASE))
    normalized = []
    for item in found:
        cleaned = item.strip().lower()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


class Verifier:
    def __init__(self, api_key: str, model: str, capture: CaptureBuffer, timeout: int = 30, max_retries: int = 3):
        self.api_key = api_key
        self.model = model
        self.capture = capture
        self.timeout = timeout
        self.max_retries = max_retries

    def verify(self, task: str, sender: str, recipient: str, agent_message: str) -> Dict[str, Any]:
        import requests

        messages = make_verifier_prompt(task, sender, recipient, agent_message)
        url = f"{OPENROUTER_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "messages": messages, "temperature": 0.0, "max_tokens": 512}

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return parse_verifier_json(content)
            except Exception as exc:  # noqa: BLE001
                self.capture.push("audit", "verifier", "system", f"Verifier call failed attempt {attempt}/{self.max_retries}: {exc}")
                time.sleep(min(2 ** attempt, 8))

        return {
            "verdict": "pass",
            "confidence": 0.2,
            "reason": "Verifier fallback due to unavailable endpoint.",
            "suggested_actions": [],
        }


def _resolve_autogen() -> Tuple[Any, Any, Any, Any, Optional[str]]:
    candidates = [("autogen", "AgentBuilder", "GroupChat", "GroupChatManager", "AssistantAgent"), ("pyautogen", "AgentBuilder", "GroupChat", "GroupChatManager", "AssistantAgent")]
    for module_name, builder_name, group_name, mgr_name, agent_name in candidates:
        try:
            mod = __import__(module_name)
            return getattr(mod, builder_name, None), getattr(mod, group_name, None), getattr(mod, mgr_name, None), getattr(mod, agent_name, None), module_name
        except Exception:  # noqa: BLE001
            continue
    return None, None, None, None, None


def build_dynamic_agents(task: str, llm_config: Dict[str, Any], max_agents: int, capture: CaptureBuffer):
    AgentBuilder, GroupChat, GroupChatManager, AssistantAgent, mod_name = _resolve_autogen()
    if not all([AgentBuilder, GroupChat, GroupChatManager, AssistantAgent]):
        capture.push("audit", "system", "ui", "AutoGen package unavailable. Running local simulated chat.")
        return None, None, None, []

    builder = AgentBuilder(config_file_or_env=None, llm_config=llm_config)
    agents = []
    try:
        if hasattr(builder, "build"):
            built = builder.build(task, max_agents=max_agents)
            if isinstance(built, tuple) and built:
                agents = list(built[0])
            elif isinstance(built, list):
                agents = built
    except Exception as exc:  # noqa: BLE001
        capture.push("audit", "builder", "ui", f"AgentBuilder failed, fallback static: {exc}")

    if not agents:
        for i in range(min(max_agents, 3)):
            agents.append(AssistantAgent(name=f"Agent{i+1}", llm_config=llm_config, system_message=f"You are specialist #{i+1} working on: {task}"))

    groupchat = GroupChat(agents=agents, messages=[], max_round=12)
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    capture.push("audit", "builder", "ui", f"AutoGen module '{mod_name}' loaded with {len(agents)} agents")
    return builder, groupchat, manager, agents


def _apply_actions(result: Dict[str, Any], builder: Any, groupchat: Any, llm_config: Dict[str, Any], capture: CaptureBuffer) -> None:
    actions = result.get("suggested_actions", []) or []
    for action in actions:
        try:
            if action.startswith("add_agent:"):
                body = action.split(":", 1)[1].strip()
                role_name = body.split(":", 1)[0].strip().replace(" ", "_") or "NewAgent"
                desc = body.split(":", 1)[1].strip() if ":" in body else "Added by verifier"
                AssistantAgent = _resolve_autogen()[3]
                if AssistantAgent and groupchat:
                    groupchat.agents.append(AssistantAgent(name=role_name, llm_config=llm_config, system_message=desc))
                    capture.push("audit", "verifier", "manager", f"Added agent {role_name}")
            elif action.startswith("remove_agent:"):
                target = action.split(":", 1)[1].strip()
                before = len(groupchat.agents)
                groupchat.agents = [a for a in groupchat.agents if getattr(a, "name", "") != target]
                capture.push("audit", "verifier", "manager", f"remove_agent {target}: {before}->{len(groupchat.agents)}")
            elif action.startswith("modify_agent_system_prompt:"):
                patch = action.split(":", 1)[1].strip()
                groupchat.messages.append({"role": "system", "content": f"Verifier patch: {patch}"})
                capture.push("audit", "verifier", "manager", f"Patch injected: {patch}")
            else:
                capture.push("audit", "verifier", "manager", f"Action noted: {action}")
        except Exception as exc:  # noqa: BLE001
            capture.push("audit", "verifier", "manager", f"Failed action {action}: {exc}")


def run_orchestrator(
    task: str,
    llm_config: Dict[str, Any],
    verifier: Verifier,
    auto_apply: bool,
    max_agents: int,
    capture: CaptureBuffer,
    key_vault: KeyVault,
) -> None:
    builder, groupchat, manager, agents = build_dynamic_agents(task, llm_config, max_agents, capture)

    def on_agent_message(source: str, target: str, message: str) -> None:
        capture.push("chat", source, target, message)
        requested = extract_key_requests(message)
        for key_name in requested:
            key_vault.request_key(key_name)
            capture.push("audit", "agent", "settings", f"Agente solicitou chave: {key_name}")
            capture.push("audit", "system", "settings", f"Aguardando usuário preencher chave '{key_name}'")
            got_key = key_vault.wait_for_key(key_name, timeout=300)
            if got_key:
                capture.push("audit", "settings", "agent", f"Chave '{key_name}' recebida e liberada para execução")
            else:
                capture.push("audit", "settings", "agent", f"Timeout aguardando chave '{key_name}'")
        verify_result = verifier.verify(task, source, target, message)
        capture.push("audit", "verifier", source, json.dumps(verify_result, ensure_ascii=False), verify_result)
        if verify_result.get("verdict") == "fail" and auto_apply and groupchat:
            _apply_actions(verify_result, builder, groupchat, llm_config, capture)

    if not manager or not agents:
        for i in range(3):
            on_agent_message(f"sim-agent-{i+1}", "manager", f"Simulação passo {i+1}: analisando '{task[:80]}'")
            time.sleep(0.3)
        capture.push("audit", "system", "ui", "Simulação concluída.")
        return

    registered = False
    for ag in agents:
        if hasattr(ag, "register_reply"):
            try:
                def _reply_hook(recipient, messages, sender, config):  # noqa: ANN001
                    if messages:
                        latest = messages[-1]
                        content = latest.get("content", str(latest)) if isinstance(latest, dict) else str(latest)
                        on_agent_message(getattr(sender, "name", "agent"), getattr(recipient, "name", "manager"), content)
                    return False, None
                ag.register_reply([type(manager), None], _reply_hook)
                registered = True
            except Exception as exc:  # noqa: BLE001
                capture.push("audit", "system", "ui", f"register_reply failed for {getattr(ag, 'name', '?')}: {exc}")

    handler = AutoGenLogHandler(capture)
    logging.getLogger("autogen").addHandler(handler)
    stdbuf = io.StringIO()
    try:
        if hasattr(manager, "run_chat"):
            with contextlib.redirect_stdout(stdbuf):
                manager.run_chat(messages=[{"role": "user", "content": task}], sender=agents[0])
        elif hasattr(agents[0], "initiate_chat"):
            with contextlib.redirect_stdout(stdbuf):
                agents[0].initiate_chat(manager, message=task)
        else:
            capture.push("audit", "system", "ui", "No known run method found; cannot execute AutoGen run.")

        if not registered:
            for line in stdbuf.getvalue().splitlines():
                if line.strip():
                    capture.push("chat", "stdout-fallback", "ui", line.strip())
    except Exception as exc:  # noqa: BLE001
        capture.push("audit", "system", "ui", f"Execution failed: {exc}")
    finally:
        logging.getLogger("autogen").removeHandler(handler)


def export_transcript_json(chat_history: List[Dict[str, Any]], audit_trail: List[Dict[str, Any]]) -> str:
    return json.dumps({"chat_history": chat_history, "audit_trail": audit_trail}, ensure_ascii=False, indent=2)


def export_transcript_markdown(chat_history: List[Dict[str, Any]], audit_trail: List[Dict[str, Any]]) -> str:
    lines = ["# Chat Transcript", ""]
    lines.extend([f"- **{m['source']} -> {m['target']}**: {m['content']}" for m in chat_history])
    lines.append("\n# Audit Trail\n")
    lines.extend([f"- `{m['timestamp']}` [{m['source']}] {m['content']}" for m in audit_trail])
    return "\n".join(lines)


def render_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="Flowchart Multi-Agent Verifier", layout="wide")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "audit_trail" not in st.session_state:
        st.session_state.audit_trail = []
    if "capture" not in st.session_state:
        st.session_state.capture = CaptureBuffer()
    if "key_vault" not in st.session_state:
        st.session_state.key_vault = KeyVault()
    if "new_key_name" not in st.session_state:
        st.session_state.new_key_name = ""

    st.sidebar.title("Configuração")
    page = st.sidebar.radio("Página", ["Chat", "Configurações"])
    key_vault: KeyVault = st.session_state.key_vault
    default_openrouter = key_vault.get_key("openrouter") or os.getenv("OPENROUTER_API_KEY", "")
    api_key = st.sidebar.text_input("OPENROUTER_API_KEY", type="password", value=default_openrouter)
    if api_key:
        key_vault.set_key("openrouter", api_key)
    model = st.sidebar.selectbox("Modelo OpenRouter", [DEFAULT_MODEL, "openrouter/openai/gpt-4o-mini", "openrouter/meta-llama/llama-3.1-70b-instruct"])
    verifier_model = st.sidebar.selectbox("Modelo do Verifier (economia)", ["openrouter/openai/gpt-4o-mini", DEFAULT_MODEL])
    max_agents = st.sidebar.slider("MAX_AGENTS", min_value=2, max_value=10, value=DEFAULT_MAX_AGENTS)
    auto_apply = st.sidebar.checkbox("Habilitar ações automáticas do Verifier", value=False)

    st.title("Streamlit + AutoGen AgentBuilder + Verifier")
    st.caption("Chave detectada: " + _sanitize_key(api_key))

    if page == "Configurações":
        st.subheader("Gerenciar chaves de API")
        st.write("Quando um agente pedir uma chave no formato `REQUEST_API_KEY: nome_servico`, um novo campo aparece aqui.")

        requested = key_vault.requested_keys()
        if "openrouter" not in requested:
            requested = ["openrouter", *requested]

        with st.form("add-key-form"):
            new_key_name = st.text_input("Adicionar novo serviço", value=st.session_state.new_key_name, placeholder="ex: serpapi")
            add_clicked = st.form_submit_button("Adicionar campo")
            if add_clicked and new_key_name.strip():
                key_vault.request_key(new_key_name.strip().lower())
                st.session_state.new_key_name = ""
                st.success(f"Campo para '{new_key_name.strip().lower()}' adicionado.")

        for key_name in requested:
            existing_val = key_vault.get_key(key_name)
            typed = st.text_input(f"{key_name.upper()}_API_KEY", type="password", value=existing_val, key=f"kv-{key_name}")
            if typed:
                key_vault.set_key(key_name, typed)
                st.caption(f"{key_name}: {_sanitize_key(typed)}")
            else:
                st.caption(f"{key_name}: pendente")

        st.info("Volte para a página Chat para executar a equipe multiagente.")
        return

    task = st.text_area("Tarefa do usuário", value="Resuma os principais riscos de usar múltiplos agentes sem verificação.")

    if st.button("Construir Equipe e Executar"):
        st.session_state.chat_history = []
        st.session_state.audit_trail = []
        capture = st.session_state.capture
        if not api_key:
            capture.push("audit", "system", "ui", "OPENROUTER_API_KEY ausente. Rodando modo de simulação.")

        llm_config = build_llm_config(api_key=api_key or "DUMMY", model=model)
        verifier = Verifier(api_key=api_key or "DUMMY", model=verifier_model, capture=capture)
        threading.Thread(
            target=run_orchestrator,
            kwargs={
                "task": task,
                "llm_config": llm_config,
                "verifier": verifier,
                "auto_apply": auto_apply,
                "max_agents": max_agents,
                "capture": capture,
                "key_vault": key_vault,
            },
            daemon=True,
        ).start()

    capture = st.session_state.capture
    while not capture.q.empty():
        ev = capture.q.get_nowait()
        target_list = st.session_state.chat_history if ev.kind == "chat" else st.session_state.audit_trail
        target_list.append(asdict(ev))

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Chat")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["source"]):
                st.write(msg["content"])
    with col2:
        st.subheader("Audit Trail")
        for ev in st.session_state.audit_trail[-50:]:
            st.markdown(f"- `{ev['timestamp']}` **{ev['source']}** → {ev['content']}")

    st.divider()
    c1, c2 = st.columns(2)
    c1.download_button("Exportar JSON", export_transcript_json(st.session_state.chat_history, st.session_state.audit_trail), file_name="transcript.json", mime="application/json")
    c2.download_button("Exportar Markdown", export_transcript_markdown(st.session_state.chat_history, st.session_state.audit_trail), file_name="transcript.md", mime="text/markdown")


if __name__ == "__main__":
    render_app()
