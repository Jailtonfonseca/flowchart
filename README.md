# Flowchart Multi-Agent App (Streamlit + AutoGen + OpenRouter)

Aplicação Streamlit que monta uma equipe dinâmica com AutoGen AgentBuilder, executa GroupChat e valida cada mensagem com um **Verifier** baseado em OpenRouter.

## Recursos principais

- UI Streamlit com:
  - Entrada de `OPENROUTER_API_KEY` (senha)
  - Página de **Configurações** para gerenciar múltiplas API keys do usuário
  - Seleção de modelo
  - Controle de `MAX_AGENTS`
  - Toggle para auto-aplicar ações sugeridas pelo Verifier
- Construção dinâmica de equipe via AgentBuilder (com fallback para simulação local)
- Captura de mensagens por prioridade de fallback:
  1. `register_reply` dos agentes
  2. callbacks em nível de manager (quando disponíveis)
  3. `logging.Handler` no logger do AutoGen
  4. `redirect_stdout` e parsing heurístico
- Verifier com saída JSON estrita (`verdict`, `confidence`, `reason`, `suggested_actions`, `patch_for_agent`)
- Audit Trail com timeline e exportação de transcript em JSON/Markdown
- Docker + docker-compose (porta 8501)

## Estrutura

- `app.py`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `tests/`
- `scripts/smoke_run.sh`
- `CHANGELOG.md`

## Configuração

1. Copie as variáveis:

```bash
cp .env.example .env
```

2. Preencha:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (opcional)
- `MAX_AGENTS` (opcional)

> Nunca commitar `.env` real.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Rodar com Docker Compose

```bash
docker compose up --build -d
docker compose logs -f
```

Aplicação disponível em: `http://localhost:8501`

## Testes

```bash
pytest tests/
```

Smoke test de container:

```bash
./scripts/smoke_run.sh
```


## Solicitação dinâmica de chaves por agentes

Se um agente emitir uma mensagem contendo:

- `REQUEST_API_KEY: <servico>`
- `NEED_API_KEY: <servico>`

o app cria automaticamente o campo correspondente na página **Configurações** e o worker aguarda o preenchimento da chave pelo usuário (timeout configurado no código).

Exemplo:

```text
REQUEST_API_KEY: serpapi
```

Após preencher a chave em Configurações, a execução é liberada e o evento aparece no Audit Trail.

## OpenRouter request format

```python
url = "https://openrouter.ai/api/v1/chat/completions"
headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type":"application/json"}
payload = {
  "model": OPENROUTER_MODEL,
  "messages": [
    {"role":"system","content":"..."},
    {"role":"user","content":"..."}
  ],
  "temperature": 0.0,
  "max_tokens": 512
}
```

## Notas sobre AutoGen (versões de pacote)

A família AutoGen pode variar:

- `autogen`
- `pyautogen`
- `autogen-agentchat`

Se o import falhar, ajuste o pacote no `requirements.txt` e os imports no `app.py`.

## Segurança, custo e performance

- Use modelo de verificação menor (ex.: `gpt-4o-mini`) para reduzir custo.
- Defina limites de tokens e rate limit por minuto.
- Sanitizar logs/transcripts para remover dados sensíveis.
- Para produção, mover worker para backend (FastAPI + WebSocket), deixando Streamlit só como frontend.
