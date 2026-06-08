# FGOS — Catálogo de Eventos

> Todo evento usa o envelope canônico ([ARCHITECTURE.md](ARCHITECTURE.md) §1). O nome segue
> `namespace.entidade.acao`, minúsculo. Produtores publicam; o `worker-router` espelha **todos**
> os eventos de `stream:events` para `stream:bi.events`, de onde o `worker-bi` grava no ClickHouse.

## Streams

| Stream | Papel |
|---|---|
| `stream:webhooks.meta` | webhooks crus do Meta (antes de virar evento de negócio) |
| `stream:events` | barramento canônico de eventos de negócio |
| `stream:bi.events` | espelho consumido pelo BI |

## Eventos de negócio (`stream:events`)

| Evento | Produtor | Disparado quando | `data` principal |
|---|---|---|---|
| `workspace.created` | api (A) | cria workspace | `workspace_id, name` |
| `workspace.item.created` | api (A) / worker-social | cria item (ou tarefa de reconexão) | `item_id, list_id, title, convert_to_deal, value_cents` |
| `crm.deal.created` | api (D) / worker-router | cria deal (manual ou a partir de item) | `deal_id, pipeline_id, stage_id, value_cents` |
| `crm.deal.moved` | api (D) | move card no Kanban | `deal_id, stage_id, version` |
| `social.account.connected` | api (B) | conecta conta OAuth | `social_account_id, platform` |
| `social.post.scheduled` | api (B) | agenda post | `post_id, social_account_id, scheduled_at` |
| `social.post.published` | worker-social | publica com sucesso | `post_id, platform, platform_post_id` |
| `social.post.failed` | worker-social | falha inválida/rede (dead-letter ou retry) | `post_id, outcome, error` |
| `social.account.rate_limited` | worker-social | 429 → pausa a conta | `social_account_id, platform` |
| `social.account.disconnected` | worker-social | 401/403 → token morto | `social_account_id, platform` |
| `messaging.session.buffered` | worker-messaging-flusher | debounce drena buffer | `session_id, text` |

## Eventos de ingestão (`stream:webhooks.meta`)

| Evento | Produtor | Consumidor |
|---|---|---|
| `webhook.meta.received` | ingest | worker-messaging |

## Quem reage a quê

| Consumidor | Lê | Faz |
|---|---|---|
| `worker-router` | `stream:events` | `workspace.item.created` + `convert_to_deal` → cria `crm.deal.created` (child, `hops+1`); **espelha todo evento** → `stream:bi.events` |
| `worker-bi` | `stream:bi.events` | micro-batch → ClickHouse `events_log` |
| `worker-messaging` | `stream:webhooks.meta` | extrai mensagem, joga no buffer de debounce |
| `worker-messaging-flusher` | (timer Redis) | drena buffer → `messaging.session.buffered` |

## Idempotência e anti-loop

- Antes de processar, o worker insere em `processed_events(event_id, worker_role)` com
  `ON CONFLICT DO NOTHING`. Se já existe para aquele papel → descarta.
- `worker_role` distingue consumidores (`router`, `bi`, `default`): o mesmo `event_id` pode ser
  processado uma vez por papel, sem um anular o outro.
- Eventos gerados por automação herdam `trace_id` e incrementam `hops`. `hops > 5` → registrado em
  `event_failures` e descartado (mata loop CRM↔Mensageria).

## Convenção para novos eventos

1. Nome `namespace.entidade.acao` minúsculo (validado no `EventEnvelope`).
2. Produza via `EventEnvelope(...)` novo, ou `evento_pai.child(...)` para preservar a linhagem.
3. Publique em `stream:events` (o router cuida do espelho pro BI).
4. Documente a linha aqui.
