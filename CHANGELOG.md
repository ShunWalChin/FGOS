# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/). Versionamento por fase do
roadmap (ver [docs/OVERVIEW.md](docs/OVERVIEW.md) §5).

## [Unreleased]

### Fase 6 — Web App (React + Vite + TS)
- SPA operável em `web/`: login → Dashboard (KPIs + breakdown de BI) → CRM Kanban (colunas=stages,
  cards=deals, mover com optimistic UI + 409, criar deal).
- `lib/api.ts` (client tipado + ApiError + token) e `lib/auth.tsx` (AuthProvider) — base
  compartilhável com o app mobile (Expo).
- Backend: novos `GET /api/pipelines` e `GET /api/stages` (necessários para o Kanban) → 39 rotas.
- **Compila de verdade**: `tsc --noEmit` (sem erros de tipo) + `vite build` (41 módulos, ~57 KB gzip).
- Tema FAT Tech sem framework de CSS; `node_modules/`/`dist/` fora do git.

### Fase 5 — Auth multi-tenant + onboarding self-service + white-label
- **Auth stdlib** (`auth.py`): JWT HS256 + senha PBKDF2 (sem PyJWT/passlib). `api/auth.py`
  (register/login/me), `api/deps.py` (`get_principal` com bypass de dev), CORS no `main.py`.
- **Onboarding self-service** (`api/onboarding.py`): `POST /api/onboarding/signup` provisiona
  agência + owner + pipeline/stages/workspace/list numa transação e devolve token (auto-login).
  `check-slug`, branding público/privado.
- **White-label**: `agencies.slug/plan/branding` (migration 006); `slug.py` (`slugify`,
  `merge_branding` puros); casca `onboarding/index.html` que se tema por agência via `?org=slug`.
- `app_users.password_hash` (migration 005); `fgos seed` cria login dev `dev@fgos.local/fgosdev`.
- Evento `agency.provisioned`. App FastAPI sobe com 37 rotas (validado via import real).
- 17 testes novos (auth + slug/branding); **50 testes no total**, todos verdes.

### Fase 4 — BI (dashboards sobre ClickHouse)
- **API de leitura** `/api/bi/{summary,timeseries,breakdown,funnel,health}` consultando **só** o
  ClickHouse (CQRS), com builders puros (`bi_queries.py`) e binding `{name:Type}` (sem interpolação).
- **Dashboard ECharts** em `/dashboard` (KPIs, série temporal, breakdown, funil) com identidade FAT Tech.
- `clickhouse_client.py` compartilhado (worker-bi escreve, api/bi lê).
- 5 testes de query builders.

### Fase 3 — Mensageria & IA (estrutural)
- **State machine** de conversa pura e testável (`messaging/flow.py`, `advance`): saudação →
  qualificação → IA/handoff, com captura de contexto.
- **IA por API externa** atrás de boundary (`providers/llm.py`): `DryRunLLM` default + `AnthropicLLM`
  skeleton; roda fora do hot path (no flusher, pós-debounce).
- **Envio outbound** atrás de boundary (`providers/messenger.py`), dry-run por padrão.
- **Worker reescrito**: inbound persiste contato/sessão/mensagem (dedupe `provider_msg_id`) +
  debounce; flusher roda a state machine, chama IA quando preciso, envia, atualiza sessão.
- **Handoff bot→humano** (`mode=human` silencia o bot) + evento `messaging.session.handoff`.
- Migration 004 (índices de lookup); eventos `messaging.message.inbound/outbound`,
  `messaging.session.handoff`. 9 testes novos.
- **Fix**: Dockerfile copiava `shared-lib/` inexistente (quebrava build) e agora copia `dashboard/`.

### Fase 2 — Social/Ads (estrutural)
- **Cripto de token em repouso** via pgcrypto (`pgp_sym_encrypt`/`pgp_sym_decrypt`), chave em
  `TOKEN_ENCRYPTION_KEY`. Tokens nunca retornados pela API.
- **`worker-social` reescrito** com tratamento do "API Hell": classificação de erro
  (`ErrorKind`), `plan_post_action` (decisão pura), pausa por conta no 429, desconexão no
  401/403 + criação de tarefa de reconexão, dead-letter de payload inválido, backoff de rede.
- **Claim seguro** (`FOR UPDATE OF pq SKIP LOCKED`) que pula contas desconectadas ou em cooldown.
- **API social**: `POST/GET /api/social-accounts`, `POST/GET /api/posts`,
  `GET /api/oauth/{platform}/authorize`, `GET /api/oauth/{platform}/callback`.
- **Provider boundary**: `DryRunProvider` (default offline) + `registry` por plataforma; adapters
  reais ativáveis com `SOCIAL_LIVE=true`.
- **Migration 003**: `social_accounts.rate_limited_until`, `posts_queue.platform_post_id`, índices.
- **Eventos novos**: `social.account.connected`, `social.post.scheduled/published/failed`,
  `social.account.rate_limited/disconnected`.
- **Docs consolidadas**: `docs/OVERVIEW.md`, `docs/API.md`, `docs/EVENTS.md`,
  `docs/MODULE-B-SOCIAL.md`, este CHANGELOG.
- **Testes**: 19 no total (10 novos para o módulo social, lógica pura).

## [0.1.0] — 2026-06-08 — FGOS nasce

### Fase 0 + 1 — Espinha + Workspace + CRM (MVP)
- Repositório FGOS criado e publicado: https://github.com/ShunWalChin/FGOS
- Envelope canônico (`EventEnvelope`) com idempotência (`event_id`/`worker_role`) e
  anti-loop (`trace_id`/`hops`).
- Espinha Redis Streams + runtime de worker.
- Módulo A (Workspace) e D (CRM) com API REST publicando eventos.
- `worker-router`: item→deal cross-módulo + espelho de todos os eventos para o BI.
- `worker-bi`: micro-batch para ClickHouse `events_log`.
- `worker-messaging`: debounce de mensagens (consolidação 2s).
- Migrations Postgres + ClickHouse; `fgos seed`; `scripts/smoke_mvp.py` end-to-end.
- LICENSE MIT (trabalho original FAT Tech); docker-compose ARM64/OCI.
