# Módulo Intelligence

Camada modular de IA do FGOS, inspirada nos estudos dos projetos SantanderAI e reescrita no padrão
do core: FastAPI, Postgres tenant-scoped, Redis Streams como evento best-effort e dry-run por padrão.

## Peças entregues

| Peça | Onde fica | Uso no produto |
|---|---|---|
| LLM Bridge | `core_engine.ai.llm_bridge`, `providers/llm.py` | OpenAI, Anthropic, Groq ou endpoint compatível atrás da boundary existente. |
| Guardrails | `core_engine.ai.guardrails` | Gate padrão em Mensageria/Growth e avaliação manual na dashboard. |
| RAG por agência | `knowledge_bases`, `knowledge_documents`, `knowledge_chunks` | Bases de produto/FAQ por agência, busca e resposta opcional com LLM. |
| Governança IA | `core_engine.ai.governance`, `ai_governance_audits` | Regimes `manual`, `semi`, `auto` para aprovar/reter ações. |
| BANT / Lead score | `core_engine.ai.scoring`, `lead_score_history`, colunas em `deals` | Prioridade comercial, temperatura e próxima ação no CRM. |
| Vault operacional | `ai_vault_notes` | Memória de metodologias, decisões e pitfalls da operação. |

## API

Todas as rotas ficam sob `/api/intelligence`:

- `POST /llm/complete`
- `GET|POST /guardrails/policies`
- `POST /guardrails/evaluate`
- `GET|POST /knowledge-bases`
- `POST /knowledge-bases/{id}/documents`
- `POST /knowledge-bases/{id}/query`
- `POST /governance/evaluate`
- `GET /governance/audits`
- `POST /lead-score`
- `GET|POST /vault/notes`
- `GET /vault/search?q=...`

## Operação

Aplicar schema:

```powershell
docker compose --profile migrate up migrate-postgres
```

Ativar LLM real:

```env
MESSAGING_LLM_LIVE=true
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=...
```

Sem chave, o sistema usa dry-run determinístico. Sem Redis local fora do Docker, a API de
inteligência continua respondendo e registra aviso; em produção os eventos voltam a ser publicados
normalmente.

## UI

A dashboard está em `/intelligence` no web app e reúne as seis ferramentas em abas.

