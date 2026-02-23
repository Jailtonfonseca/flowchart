# Changelog

## 0.1.0
- App Streamlit com AgentBuilder + GroupChat + Verifier.
- Verifier com prompt JSON estrito e ações sugeridas/auto-aplicáveis.
- Fallbacks de captura: register_reply, logger, stdout.
- Dockerfile e docker-compose para execução em porta 8501.
- Testes básicos com pytest e smoke script.

## Como ajustar o verificador
- Modifique `temperature` (padrão 0.0) em `Verifier.verify`.
- Ajuste o modelo no sidebar (`verifier_model`) para reduzir custos.
- Defina regras adicionais no prompt em `make_verifier_prompt`.
- Altere limiar/estratégia para `verdict == fail` na função `run_orchestrator`.
