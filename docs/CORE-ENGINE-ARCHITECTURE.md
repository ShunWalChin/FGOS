# Core-Engine Architecture

## Decisoes

1. Redis Streams e a espinha dorsal inicial. NATS JetStream fica para uma fase de escala maior.
2. n8n e consumidor de integracoes, nao message bus.
3. LLM em producao roda por API externa. Sem Ollama 7B no caminho quente da OCI Ampere A1.
4. Postgres guarda transacoes. ClickHouse guarda leitura analitica.
5. Todo evento e multi-tenant, idempotente e rastreavel por `trace_id`.

## Topologia

```text
Traefik/Caddy
  |-- /webhooks/* --> ingest FastAPI --> stream:webhooks.meta
  |-- /api/*      --> api FastAPI    --> stream:events

Redis Streams
  |-- worker-messaging
  |-- worker-social
  |-- worker-bi
  |-- n8n-webhook/n8n-worker

Postgres 16: agencias, CRM, produtividade, mensageria, fila social, idempotencia
ClickHouse: events_log
```

## Hot Path

1. Webhook chega na borda.
2. FastAPI valida assinatura HMAC.
3. Payload cru vira `webhook.meta.received`.
4. Evento entra no Redis Stream.
5. API responde `200 OK` sem logica de negocio.
6. Workers consomem com grupo Redis, verificam `processed_events` e processam.

## Modulos

- Produtividade: `workspaces`, `lists`, `items`, JSONB para campos dinamicos e `version` para optimistic locking.
- Social: `social_accounts` e `posts_queue` com backoff e `FOR UPDATE SKIP LOCKED`.
- Mensageria: `contacts`, `chat_sessions`, `messages`, dedupe por `provider_msg_id`.
- CRM: `pipelines`, `stages`, `deals`, dinheiro em `value_cents`.
- BI: eventos em micro-batch para ClickHouse.

## Fases

1. Infra, migrations, contrato de evento e idempotencia.
2. Workspace + CRM trocando eventos reais.
3. Social com OAuth, backoff por conta e fila segura.
4. Mensageria com debounce e IA por API.
5. BI com dashboards sobre ClickHouse.
