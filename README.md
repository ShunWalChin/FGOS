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
| **A — Produtividade** | ClickUp / Monday | API + eventos no MVP | `workspaces`, `lists`, `items` (JSONB + `version`) |
| **D — CRM** | Pipedrive | API + Kanban move (409) no MVP | `pipelines`, `stages`, `deals` (`value_cents`) |
| **B — Social/Ads** | Hootsuite | fila `SKIP LOCKED` + backoff | `social_accounts`, `posts_queue` |
| **C — Mensageria/IA** | ManyChat | debounce + IA por API externa | `contacts`, `chat_sessions`, `messages` |
| **E — BI** | PowerBI | micro-batch → ClickHouse | `events_log` (MergeTree) |

## MVP — espinha em 4 comandos

Valida a fase 1 do roadmap: um evento nasce no **Workspace**, atravessa a fila e cria um **deal**
no CRM, com idempotência e anti-loop ativos, e espelhamento para o ClickHouse (BI).

```powershell
copy .env.example .env

# 1. infra + migrations
docker compose --profile migrate up migrate-postgres migrate-clickhouse
docker compose up -d postgres redis clickhouse api worker-router worker-bi

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
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **Fonte da verdade** — EDT completa: contrato de eventos, DDL por módulo, código crítico, API Hell, CQRS, backups, roadmap |
| [docs/EXTRACTION-INTEGRATION-KB.md](docs/EXTRACTION-INTEGRATION-KB.md) | Rota alternativa de escala: integrar OSS validado (Plane/Twenty/Postiz/Evolution/Superset) em vez de reescrever |
| [docs/CORE-ENGINE-ARCHITECTURE.md](docs/CORE-ENGINE-ARCHITECTURE.md) | Decisões condensadas do runtime atual |
| [neural-base/](neural-base/) | Base de conhecimento para agentes de IA (knowledge graph, facts, ADRs, glossário) — alimenta assistentes que trabalham no FGOS |

## Roadmap honesto

| Fase | Entrega |
|---|---|
| **0** ✅ | Infra + contrato de evento + idempotência + espinha Redis Streams |
| **1** ✅ (MVP) | Workspace + CRM trocando eventos reais pela fila, com BI espelhado |
| **2** | Social/Ads: OAuth, backoff por conta, `SKIP LOCKED` |
| **3** | Mensageria: debounce + IA por API externa + state machine |
| **4** | BI: dashboards sobre ClickHouse (Superset embarcado ou ECharts) |
| **5** | Casca white-label + onboarding self-service por agência |

## Operação

```bash
docker compose ps
docker compose logs -f worker-router
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" XLEN stream:events
docker stats --no-stream
```

Backups off-box não são opcionais numa VPS única: dump diário do Postgres, backup nativo do
ClickHouse e cópia do AOF do Redis para OCI Object Storage. Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §9.

## Licença e atribuição

MIT. FGOS deriva do redesenho Python do projeto **GrowthOS**; o trabalho original de base é de
Rafael Melga ([github.com/melgarafael](https://github.com/melgarafael)). Consolidação, runtime
event-driven e identidade FGOS por **Walfredo Figueiredo Neto / FAT Tech**. Ver [LICENSE](LICENSE) e [FGOS.md](FGOS.md).

---

<p align="center"><sub>Desenvolvido com IA pela <strong>FAT Tech</strong> · <a href="https://fattech.com.br">fattech.com.br</a> · Januária, MG — Brasil</sub></p>
