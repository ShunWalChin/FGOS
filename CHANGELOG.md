# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/). Versionamento por fase do
roadmap (ver [docs/OVERVIEW.md](docs/OVERVIEW.md) §5).

## [Unreleased]

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
