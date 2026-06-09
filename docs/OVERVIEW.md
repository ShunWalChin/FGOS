# FGOS — Visão Consolidada do Projeto

> Documento mestre. Leia este primeiro: ele amarra arquitetura, módulos, dados,
> eventos e operação num só lugar e aponta para os documentos profundos.
> Fonte da verdade arquitetural: [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. O que é

FGOS (FAT Tech Growth Operacional System) unifica, num único ecossistema modular para
agências de marketing:

| Módulo | Referência | Faz |
|---|---|---|
| **A — Produtividade** | ClickUp/Monday | tarefas, listas, campos dinâmicos (JSONB) |
| **B — Social/Ads** | Hootsuite | contas OAuth, agendamento e publicação multi-rede |
| **C — Mensageria/IA** | ManyChat | chatbots, live chat, agentes (debounce + LLM externo) |
| **D — CRM** | Pipedrive | funis Kanban, leads, deals em centavos |
| **E — BI** | PowerBI | análise consolidada via ClickHouse |
| **Acesso** | Auth/Onboarding | login JWT multi-tenant + signup self-service white-label |

Cada módulo é independente e **só fala com os outros pela coluna vertebral de eventos** —
nunca por chamada HTTP direta módulo-a-módulo.

## 2. A coluna vertebral

```text
                 produz eventos
  API / ingest ───────────────►  Redis Streams ──► worker-router ──► worker-bi ──► ClickHouse
  (FastAPI)                       (a espinha)         │  (reage +        (micro-batch)
                                                      │   espelha)
  webhooks Meta ──► ingest ──► stream:webhooks.meta ──┴─► worker-messaging (debounce)
```

Três streams:

| Stream | Conteúdo | Quem produz | Quem consome |
|---|---|---|---|
| `stream:webhooks.meta` | webhooks crus do Meta | `ingest` | `worker-messaging` |
| `stream:events` | eventos de negócio canônicos | API + workers | `worker-router` |
| `stream:bi.events` | espelho para BI | `worker-router` | `worker-bi` |

**Envelope canônico** (todo evento, ver [ARCHITECTURE.md](ARCHITECTURE.md) §1):
`event_id` (idempotência), `event` (`namespace.entidade.acao`), `agency_id` (tenant),
`trace_id` + `hops` (anti-loop), `actor`, `occurred_at`, `data`.

**Garantias do barramento:**
- **Idempotência:** `processed_events(event_id, worker_role)` — cada papel de worker processa um evento no máximo uma vez; permite que router e BI vejam o mesmo `event_id` sem um anular o outro.
- **Anti-loop:** eventos gerados por automação herdam `trace_id` e fazem `hops+1`; `hops > 5` é cortado.
- **Multi-tenant:** `agency_id` em toda tabela e todo evento.
- **Dinheiro:** sempre `bigint` em centavos.

Catálogo completo de eventos: [EVENTS.md](EVENTS.md). Referência de endpoints: [API.md](API.md).

## 3. Processos (o que roda)

| Serviço | Papel | Stream/Tabela |
|---|---|---|
| `api` | API REST de todos os módulos; publica eventos | → `stream:events` |
| `ingest` | recebe webhook Meta (HMAC), ACK <200ms | → `stream:webhooks.meta` |
| `worker-router` | reage cross-módulo (item→deal) e **espelha tudo pro BI** | `stream:events` → `stream:bi.events` |
| `worker-bi` | micro-batch para ClickHouse | `stream:bi.events` → `events_log` |
| `worker-social` | publica posts (SKIP LOCKED), trata API Hell | `posts_queue` → `stream:events` |
| `worker-messaging` | consolida mensagens (debounce 2s) | `stream:webhooks.meta` |
| `worker-messaging-flusher` | drena buffer e emite evento consolidado | → `stream:events` |
| `n8n` | cola de integrações configurável (fora do hot path) | consumidor |

## 4. Modelo de dados (Postgres OLTP)

- **A:** `workspaces` → `lists` → `items` (JSONB `fields`, `version` p/ optimistic lock)
- **B:** `social_accounts` (tokens cifrados pgcrypto, `status`, `rate_limited_until`),
  `posts_queue` (`status`, `attempts`, `next_attempt_at`, `platform_post_id`, locks)
- **C:** `contacts`, `chat_sessions`, `messages` (dedupe por `provider_msg_id`)
- **D:** `pipelines`, `stages`, `deals` (`value_cents`, `version`)
- **Acesso:** `agencies` (`slug`, `plan`, `branding` jsonb), `app_users` (`password_hash`, `role`)
- **infra:** `processed_events`, `event_failures`, `worker_heartbeats`

BI (ClickHouse): `events_log` (MergeTree, particionado por mês).

Migrations em `migrations/postgres/` e `migrations/clickhouse/`, aplicadas em ordem
numérica pelo profile `migrate` do compose.

## 5. Estado por fase

| Fase | Escopo | Estado |
|---|---|---|
| 0 | Infra + envelope + idempotência + espinha | ✅ |
| 1 | Workspace + CRM trocando eventos + BI espelhado | ✅ (MVP) |
| 2 | Social/Ads: OAuth scaffolding, cripto de token, SKIP LOCKED, backoff por conta, API Hell | ✅ estrutural (provider em dry-run; adapters reais pendentes) |
| 3 | Mensageria: debounce + IA externa + state machine + handoff | ✅ estrutural (LLM/envio em dry-run) |
| 4 | BI: API de leitura ClickHouse + dashboard ECharts | ✅ |
| 5 | Auth JWT multi-tenant + onboarding self-service + casca white-label | ✅ |
| 6 | Web App React (login → Dashboard → CRM Kanban) + base mobile | ✅ (SPA compila; telas restantes pendentes) |

Detalhe por módulo: [MODULE-B-SOCIAL.md](MODULE-B-SOCIAL.md), [MODULE-C-MESSAGING.md](MODULE-C-MESSAGING.md),
[MODULE-E-BI.md](MODULE-E-BI.md), [MODULE-AUTH-ONBOARDING.md](MODULE-AUTH-ONBOARDING.md).
Histórico: [../CHANGELOG.md](../CHANGELOG.md).

## 6. Rodar

```powershell
copy .env.example .env
docker compose --profile migrate up migrate-postgres migrate-clickhouse
docker compose up -d postgres redis clickhouse api worker-router worker-bi worker-social
docker compose exec api fgos seed
python scripts/smoke_mvp.py
```

Dev sem Docker e validação: ver [../README.md](../README.md).

## 7. Operação e riscos

- Métrica nº1: lag das streams (`XLEN`). Lag alto = subir workers, não reiniciar.
- Backups off-box (Postgres + ClickHouse + AOF do Redis) — única defesa real no single-box.
- Segredos no `.env` (fora do git). `TOKEN_ENCRYPTION_KEY` e `N8N_ENCRYPTION_KEY` em cofre.
- Tabela de riscos por módulo: [ARCHITECTURE.md](ARCHITECTURE.md) (apêndice).

## 8. Duas rotas de escala (decisão consciente)

- **Construir os módulos** (rota atual, `src/core_engine`) — controle total, sem AGPL.
- **Integrar OSS** (Plane/Twenty/Postiz/Evolution/Superset) — mais rápido, mas orquestra 7 apps
  e exige cuidado de licença. Ver [EXTRACTION-INTEGRATION-KB.md](EXTRACTION-INTEGRATION-KB.md).

## 9. Inteligência competitiva

[COMPETITOR-IMPULSE-CRM.md](COMPETITOR-IMPULSE-CRM.md) — engenharia reversa do Impulse CRM (concorrente
WhatsApp-first com IA), mapeada módulo a módulo para o FGOS, com as lacunas de produto priorizadas
(follow-ups por silêncio, fila/SLA de atendimento, BANT score, distribuição de atendentes, agenda,
financeiro). Todas viáveis como novos "plugs" no mesmo barramento de eventos.

---

Desenvolvido com IA pela **FAT Tech**.
