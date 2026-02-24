# Multi-Agent Orchestrator with Credential Manager

Sistema completo com backend FastAPI + frontend React/Vite para orquestração multi-agente (AutoGen), verificação por LLM (OpenRouter), e gerenciamento interativo de credenciais em runtime.

## Visão geral

- `backend/`: API, runner, verifier, credential store criptografado (Fernet).
- `frontend/`: UI com ConfigPanel, Settings dinâmico, Chat/Audit Trail, CredentialModal.
- `tests/`: suíte pytest com fluxos de credenciais/verifier/runner.
- `docker-compose.yml`: sobe stack local completa.

## Rodando em desenvolvimento (sem Docker)

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Rodando com Docker Compose

```bash
docker compose up --build -d
```

Healthcheck:

```bash
curl http://localhost:8000/health
```

## Testes

```bash
pytest tests
```

## Endpoints HTTP

1. `POST /start-task`
   - body: `{"task": str, "model": str, "openrouter_api_key": optional str, "max_agents": int, "auto_apply": bool, "user_id": str}`
   - response: `{"task_id": str, "ws": "/ws/{task_id}"}`
2. `POST /credentials`
   - body: `{"user_id": str, "provider": str, "value": str}`
   - response: `{"status":"ok"}`
3. `GET /credentials/{user_id}`
   - lista providers (sem segredos)
4. `POST /auth/login`
   - retorna JWT de demonstração

## WebSocket `/ws/{task_id}`

Backend -> Frontend:

- `{"kind":"agent_message", "payload":{"sender": "...", "recipient":"...", "content":"...", "ts": 12345}}`
- `{"kind":"verifier_result", "payload":{"verdict":"pass|fail", "confidence":0.0-1.0, "reason":"...", "suggested_actions":[...], "patch_for_agent": "...", "ts":12345}}`
- `{"kind":"credential_request", "payload": {"provider":"github","description":"...", "scope":"...", "request_id":"rid123", "ts":12345}}`
- `{"kind":"action_result", "payload":{"action":"add_agent|remove_agent|modify_agent_system_prompt", "detail":"...", "ts":12345}}`
- `{"kind":"info","payload":{"msg":"...","ts":12345}}`
- `{"kind":"error","payload":{"msg":"...","ts":12345}}`
- `{"kind":"finished","payload":{"msg":"...","ts":12345}}`

Frontend -> Backend (opcional):

- `{"cmd":"stop"}`
- `{"cmd":"approve_action","action_id":"...","approve":true}`
- `{"cmd":"credential_provided","request_id":"rid123"}`

## Segurança

- Não comite chaves no git.
- Credenciais são armazenadas com Fernet (ou plaintext só quando `DEV_MODE=true`).
- Não há exposição de segredo em logs/eventos.
- Em produção, substitua Fernet por Vault/Secrets Manager.

### Exemplo de substituição por Vault

1. Introduza `VaultCredentialStore` com `hvac`.
2. Troque DI em `backend/app/main.py` para usar Vault em produção.
3. Guarde somente ponteiros/metadados localmente.

## AutoGen compatibility

Dependendo da versão, `import autogen` pode falhar.

- tente: `pip install autogen-agentchat`
- fallback: `pip install pyautogen`
- ajuste imports conforme versão da lib

## Fluxos manuais sugeridos

1. Tarefa simples:
   `Liste 3 fontes públicas confiáveis sobre 'API rate limiting' e, se precisar de GitHub token, peça a credencial.`
2. Simular fail do verifier com ações:
   `modify_agent_system_prompt: Cite sources or say I don't know`, `request_references`.

## Notas

- Timeout padrão do verifier: 30s com retries exponenciais.
- Circuit breaker simples evita spam de falhas no provedor remoto.
