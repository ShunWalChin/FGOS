# Agent Primer — Project Core-Engine

Cole isto como contexto/system de um agente de código (Claude Code, Cursor, etc.). É a versão densa da base neural; o detalhe completo está em `00_MASTER_KNOWLEDGE_BASE.md`.

## O que é
SaaS modular para agência de marketing unificando produtividade (ClickUp), social/ads (Hootsuite), mensageria/IA (ManyChat), CRM com IA (Pipedrive) e BI (PowerBI). Arquitetura orientada a eventos. Roda em ARM64 (OCI Ampere).

## Verdades não-negociáveis (não viole)
1. A espinha dorsal é **Redis Streams + consumidores finos**, NÃO o n8n. n8n é cola de integração, fora do hot path de webhooks.
2. LLM em produção via **API externa**; nunca Ollama no caminho de resposta de chat.
3. Estratégia é **integrar OSS rodando como serviço** (API/webhook/MCP), nunca colar o código deles no nosso repo. Fork só cirúrgico.
4. AGPL não contamina o que fala por rede; contamina o que se mistura no código. Mantenha processos separados.
5. Dinheiro = `bigint` centavos. Imagens Docker = versão pinada (nunca `:latest`).
6. Multi-tenant: `agency_id` em toda tabela e em todo evento.

## Contratos de código
- **Envelope de evento**: `{event_id, event, version, agency_id, occurred_at, actor, trace_id, hops, data}`.
- **Idempotência**: insert em `processed_events(event_id)` com ON CONFLICT DO NOTHING; 0 linhas → descarta.
- **Anti-loop**: herdar `trace_id`, incrementar `hops`; `hops>5` → descarta.
- **Fila de posts**: `FOR UPDATE SKIP LOCKED`; falha → backoff `now()+power(3,attempts) min`.
- **Kanban**: optimistic locking via `version`; mismatch → 409 + rollback no front.
- **Mensageria**: debounce 2s antes do LLM.
- **BI**: CQRS; ClickHouse para leitura; Superset embed com guest token + RLS por tenant.
- **Ingest**: valida HMAC, XADD no stream, responde 200 em <200ms, zero lógica.

## Stack OSS por módulo (rodar como serviço)
- Workspace → makeplane/plane (AGPL) · CRM → twentyhq/twenty (AGPL, MCP) · Social → gitroomhq/postiz-app (AGPL, nó n8n) · WhatsApp → EvolutionAPI/evolution-api (Apache, eventos NATS) · Chatbot → typebot.io (AGPL) · Live chat → chatwoot/chatwoot (fork white-label) · BI → apache/superset (Apache) sobre ClickHouse · Orquestrador → n8n (fair-code) ou activepieces (MIT, se embutir).

## O que construímos (não existe pronto)
Control Plane (modelo canônico + `app_entity_map` + provisionamento), Event Spine (ingest + adapters + workers), SSO/OIDC (Authentik), BI embarcado (guest tokens), casca white-label.

## Repos próprios (polyrepo)
`core-control-plane`, `core-event-spine`, `core-frontend`, `core-infra`, `core-forks/chatwoot`.

## Ordem de construção
Fase 0 infra+SSO+backups+contrato de evento → Fase 1 Plane+Twenty provisionados → Fase 2 adapters Plane↔Twenty → Fase 3 Postiz via n8n → Fase 4 Mensageria+IA → Fase 5 ClickHouse+Superset embed → Fase 6 white-label. Sempre provar o ciclo provisionar→evento→automação antes de adicionar módulo.

## Operação
Lentidão? Olhe o lag da fila (`XLEN`), não reinicie a VPS. Escale com `--scale n8n-worker=N`.
