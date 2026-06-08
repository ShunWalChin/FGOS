# Módulo E — Business Intelligence (fase 4)

> O "PowerBI interno". Lê **só** do ClickHouse (CQRS), serve uma API fina de
> agregações e um dashboard ECharts com a identidade FAT Tech.

## Componentes

| Arquivo | Papel |
|---|---|
| `clickhouse_client.py` | client compartilhado (worker-bi escreve, api/bi lê) |
| `bi_queries.py` | builders **puros** de SQL (`summary`/`timeseries`/`breakdown`/`funnel`) |
| `api/bi.py` | endpoints `/api/bi/*` que executam os builders no ClickHouse |
| `dashboard/index.html` | dashboard ECharts (CDN) servido em `/dashboard` |
| `workers/bi.py` | micro-batch dos eventos → `events_log` (já existia, fase 0) |

## CQRS na prática

```text
stream:events ─► worker-router ─► stream:bi.events ─► worker-bi ─► ClickHouse.events_log
                                                                        │
                                                  api/bi.py (SELECT agregado) ◄── dashboard ECharts
```

- **Escrita:** o `worker-bi` insere eventos em micro-batch (a cada `BI_FLUSH_SECONDS` ou
  `BI_BATCH_SIZE`). ClickHouse foi feito para inserts massivos, não unitários.
- **Leitura:** a API de BI consulta **somente** o ClickHouse — nunca o Postgres transacional —
  evitando deadlock/contention (docs/ARCHITECTURE.md §7).

## Endpoints (`/api/bi`)

| Rota | Retorna |
|---|---|
| `GET /api/bi/summary?agency_id` | KPIs: total de eventos, tipos, valor em deals (centavos), posts publicados, msgs in/out |
| `GET /api/bi/timeseries?agency_id&days=30` | contagem de eventos por dia |
| `GET /api/bi/breakdown?agency_id&limit=20` | contagem por tipo de evento |
| `GET /api/bi/funnel?agency_id` | eventos `crm.*` (funil) |
| `GET /api/bi/health` | liveness do ClickHouse |

Toda query usa **binding `{name:Type}`** do ClickHouse — `agency_id` nunca é interpolado na string
(testado em `tests/test_bi_queries.py`).

## Dashboard

`GET /dashboard/` serve `dashboard/index.html` (ECharts via CDN). Renderiza KPIs, série temporal,
breakdown por tipo e funil CRM, consumindo a API de BI. Paleta FAT Tech (cyan `#00f0ff`, pink
`#ff2d78`, purple `#a855f7`), fontes Orbitron/Rajdhani/Share Tech Mono. Campo para trocar o
`agency_id`.

> Servido pela própria `api` (StaticFiles) se a pasta `dashboard/` existir no CWD — incluída na
> imagem Docker. A rota OSS alternativa (Superset embarcado + guest tokens com RLS) está documentada
> em [EXTRACTION-INTEGRATION-KB.md](EXTRACTION-INTEGRATION-KB.md) §3.4; aqui ficamos no stack próprio.

## Por que ECharts e não Superset

Para o MVP, ECharts + API fina é **100% dentro do nosso stack** (sem subir mais um serviço pesado),
demonstra o CQRS de ponta a ponta e cabe no box. Superset embarcado entra quando precisarmos de
dashboards self-service editáveis pelo cliente com RLS por tenant.

## O que falta

- Agregações pré-materializadas (ClickHouse `MATERIALIZED VIEW`) para volumes grandes.
- Filtros por período/cliente no dashboard.
- Guest tokens / RLS se migrar para Superset embarcado.

## Testes

`tests/test_bi_queries.py`: todos os builders (binding correto, clamps de `days`/`limit`, filtro
`crm.%`, e a garantia de que `agency_id` nunca entra na string SQL).
