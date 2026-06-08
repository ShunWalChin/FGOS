<!-- FGOS — FAT Tech Growth Operacional System -->

<h1 align="center">FGOS</h1>
<p align="center"><strong>FAT Tech Growth Operacional System</strong></p>
<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-MVP%20operacional-00f0ff?style=for-the-badge&labelColor=06060e">
  <img alt="stack" src="https://img.shields.io/badge/stack-Python%20%7C%20FastAPI%20%7C%20Redis%20Streams-ff2d78?style=for-the-badge&labelColor=06060e">
  <img alt="arch" src="https://img.shields.io/badge/arquitetura-Event--Driven-a855f7?style=for-the-badge&labelColor=06060e">
  <img alt="target" src="https://img.shields.io/badge/alvo-ARM64%20%2F%20OCI%20Ampere%20A1-22c55e?style=for-the-badge&labelColor=06060e">
</p>

---

FGOS é a plataforma modular da **FAT Tech** para operar uma agência de marketing de ponta a ponta:
produtividade (estilo ClickUp/Monday), social/ads (Hootsuite), mensageria com IA (ManyChat),
CRM com funil Kanban (Pipedrive) e BI consolidado (PowerBI) — tudo costurado por uma
**coluna vertebral orientada a eventos**.

A decisão central, validada após várias iterações de arquitetura: **n8n não é o barramento do
sistema**. O caminho quente usa **FastAPI + Redis Streams + workers finos em Python**. O n8n entra
apenas como **um** consumidor, responsável pela cola de integrações que muda toda semana — fora da
ingestão crítica.

## Arquitetura em uma imagem

```text
Webhooks (Meta/TikTok/LinkedIn)        Frontend SPA
            │                               │
            ▼                               ▼
        ┌──────────────────────────────────────┐
        │      Traefik / Caddy (TLS, proxy)     │
        └──────────────┬───────────────┬────────┘
                 /webhooks/*        /api/*
                       │               │
                       ▼               ▼
                  ingest          api backend        (FastAPI)
                       │               │ publica eventos
                       └───────┬───────┘
                               ▼
                  ┌─────────────────────────┐
                  │  Redis Streams (espinha) │
                  └───┬──────────┬───────────┘
            ┌─────────┘          │           └──────────┐
            ▼                    ▼                      ▼
     worker-router       worker-messaging         worker-social   ...  n8n (cola)
            │                    │                      │
            ▼                    ▼                      ▼
     ┌──────────────┐                          ┌──────────────┐
     │ PostgreSQL 16│  (OLTP / core)           │  ClickHouse  │  (OLAP / BI)
     └──────────────┘                          └──────────────┘
```

Regras inegociáveis do barramento (ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)):

- Todo evento carrega um **envelope canônico** com `event_id`, `agency_id`, `trace_id`, `hops`.
- `event_id` é **chave de idempotência** (`processed_events`).
- Automações **herdam** o `trace_id` e incrementam `hops`; `hops > 5` corta loops CRM↔Mensageria.
- Dinheiro é sempre `bigint` em **centavos** — nunca float.
- Multi-tenant: `agency_id` em toda tabela e todo evento.

## Módulos

| Módulo | Referência de mercado | Estado | Tabelas-núcleo |
|---|---|---|---|
| **A — Produtividade** | ClickUp / Monday | ✅ API + eventos | `workspaces`, `lists`, `items` (JSONB + `version`) |
| **D — CRM** | Pipedrive | ✅ API + Kanban move (409) | `pipelines`, `stages`, `deals` (`value_cents`) |
| **B — Social/Ads** | Hootsuite | ✅ fila `SKIP LOCKED` + backoff por conta + OAuth (dry-run) | `social_accounts`, `posts_queue` |
| **C — Mensageria/IA** | ManyChat | ✅ debounce + state machine + IA externa + handoff (dry-run) | `contacts`, `chat_sessions`, `messages` |
| **E — BI** | PowerBI | ✅ micro-batch → ClickHouse + API de leitura + dashboard ECharts | `events_log` (MergeTree) |
| **Acesso** | Auth + Onboarding | ✅ login JWT multi-tenant + signup self-service white-label | `app_users`, `agencies` (slug/branding) |

## MVP — espinha em 4 comandos

Valida a fase 1 do roadmap: um evento nasce no **Workspace**, atravessa a fila e cria um **deal**
no CRM, com idempotência e anti-loop ativos, e espelhamento para o ClickHouse (BI).

```powershell
copy .env.example .env

# 1. infra + migrations
docker compose --profile migrate up migrate-postgres migrate-clickhouse
docker compose up -d postgres redis clickhouse api worker-router worker-bi `
  worker-social worker-messaging worker-messaging-flusher

# 2. fixtures de dev (agency, pipeline, stages, workspace, list)
docker compose exec api fgos seed

# 3. smoke end-to-end: cria item -> ve deal aparecer -> confirma BI
python scripts/smoke_mvp.py
```

O que o smoke prova:

- `POST /api/items` com `convert_to_deal=true` publica `workspace.item.created` em `stream:events`.
- `worker-router` consome, cria o deal no Postgres, emite `crm.deal.created` como `child()`
  (preserva `trace_id`, `hops+1`) e espelha tudo em `stream:bi.events`.
- `worker-bi` faz micro-batch para `events_log` no ClickHouse.

Pular checagem do ClickHouse: `python scripts/smoke_mvp.py --no-clickhouse`.

**Dashboard de BI:** depois do smoke, abra `http://localhost:8000/dashboard/` para ver KPIs,
série temporal, breakdown de eventos e funil CRM (ECharts, lendo direto do ClickHouse).

**Onboarding white-label:** abra `http://localhost:8000/onboarding/` para criar uma agência nova
(signup self-service que provisiona pipeline + workspace + owner e já loga). Login de dev pronto
após `fgos seed`: `dev@fgos.local` / `fgosdev`. Tema por agência via `/onboarding/?org=<slug>`.

## Desenvolvimento local (sem Docker)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

fgos seed
fgos api
fgos worker router
fgos worker bi
```

Validação:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
python -m compileall src
```

## Documentação

| Documento | O que é |
|---|---|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | **Comece aqui** — visão consolidada: arquitetura, módulos, dados, eventos, operação |
| [docs/API.md](docs/API.md) | Referência de todos os endpoints REST e os eventos que emitem |
| [docs/EVENTS.md](docs/EVENTS.md) | Catálogo de eventos: produtor → consumidor → payload + idempotência/anti-loop |
| [docs/MODULE-B-SOCIAL.md](docs/MODULE-B-SOCIAL.md) | Módulo Social/Ads (fase 2): cripto de token, API Hell, OAuth, dry-run vs live |
| [docs/MODULE-C-MESSAGING.md](docs/MODULE-C-MESSAGING.md) | Módulo Mensageria (fase 3): debounce, state machine, IA externa, handoff |
| [docs/MODULE-E-BI.md](docs/MODULE-E-BI.md) | Módulo BI (fase 4): CQRS, API de leitura ClickHouse, dashboard ECharts |
| [docs/MODULE-AUTH-ONBOARDING.md](docs/MODULE-AUTH-ONBOARDING.md) | Auth (fase 5): login JWT multi-tenant, onboarding self-service, white-label |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **Fonte da verdade** — EDT completa: contrato de eventos, DDL, código crítico, CQRS, backups |
| [docs/EXTRACTION-INTEGRATION-KB.md](docs/EXTRACTION-INTEGRATION-KB.md) | Rota alternativa de escala: integrar OSS (Plane/Twenty/Postiz/Evolution/Superset) |
| [docs/COMPETITOR-IMPULSE-CRM.md](docs/COMPETITOR-IMPULSE-CRM.md) | Engenharia reversa do concorrente Impulse CRM + mapeamento → FGOS + oportunidades de roadmap |
| [docs/CORE-ENGINE-ARCHITECTURE.md](docs/CORE-ENGINE-ARCHITECTURE.md) | Decisões condensadas do runtime |
| [CHANGELOG.md](CHANGELOG.md) | Histórico por fase do roadmap |
| [neural-base/](neural-base/) | Base de conhecimento para agentes de IA (knowledge graph, facts, ADRs, glossário) |

## Roadmap honesto

| Fase | Entrega |
|---|---|
| **0** ✅ | Infra + contrato de evento + idempotência + espinha Redis Streams |
| **1** ✅ (MVP) | Workspace + CRM trocando eventos reais pela fila, com BI espelhado |
| **2** ✅ | Social/Ads: OAuth (scaffolding), backoff por conta, `SKIP LOCKED`, cripto de token |
| **3** ✅ | Mensageria: debounce + state machine + IA por API externa + handoff (dry-run) |
| **4** ✅ | BI: API de leitura ClickHouse + dashboard ECharts (`/dashboard`) |
| **5** ✅ | Auth JWT multi-tenant + onboarding self-service + casca white-label (`/onboarding`) |
| **6** | Web App React (SPA operável) + base mobile (Expo) — em andamento |

## Operação

```bash
docker compose ps
docker compose logs -f worker-router
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" XLEN stream:events
docker stats --no-stream
```

Backups off-box não são opcionais numa VPS única: dump diário do Postgres, backup nativo do
ClickHouse e cópia do AOF do Redis para OCI Object Storage. Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §9.

## Licença

MIT © **Walfredo Figueiredo Neto / FAT Tech**. O runtime event-driven e a identidade FGOS são
trabalho original da FAT Tech. Ver [LICENSE](LICENSE) e [FGOS.md](FGOS.md).

---

<p align="center"><sub>Desenvolvido com IA pela <strong>FAT Tech</strong> · <a href="https://fattech.com.br">fattech.com.br</a> · Januária, MG — Brasil</sub></p>
