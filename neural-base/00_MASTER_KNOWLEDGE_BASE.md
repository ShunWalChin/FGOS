# Project Core-Engine — Base Neural Completa (Knowledge Export)

> **Fonte única de verdade do projeto.** Este arquivo consolida toda a engenharia decidida: arquitetura, plano de extração/integração de OSS, e a pesquisa de mercado.
> Ele é a camada legível por humanos do export. As camadas estruturadas (para IA/RAG) estão em `knowledge_graph.json`, `facts.jsonl`, `glossary.json` e `decisions_adr.json`.
> Para alimentar um agente de código, use `agent_primer.md`. Para busca semântica local, rode `build_vector_index.py`.

## Sumário do projeto em 7 linhas
1. SaaS modular para agência de marketing = ClickUp + Hootsuite + ManyChat + PowerBI + CRM com IA num só ecossistema.
2. Paradigma: arquitetura orientada a eventos (EDA); **a espinha dorsal NÃO é o n8n** — é Redis Streams + consumidores finos.
3. n8n/Activepieces entram como **cola de integração**, fora do caminho quente de webhooks.
4. LLM em **produção via API externa** (não Ollama local — não cabe no box ARM sob carga).
5. Estratégia central: **integrar OSS maduro rodando como serviço**, não reescrever nem colar código (proteção AGPL + manutenção).
6. Você constrói só a camada de unificação: SSO, Control Plane, Event Spine, BI embarcado, casca white-label.
7. Cabe num box de 24 GB **ou** integra OSS multi-box — são rotas mutuamente exclusivas.

## Pesquisa de mercado — OSS validados (estrelas/licença, jun/2026)

| Módulo | Repo | ⭐ aprox. | Licença | Papel |
|---|---|---|---|---|
| Workspace/Tarefas | makeplane/plane | ~50k | AGPL-3.0 | Alternativa Jira/Linear/Monday/ClickUp |
| Docs/Wiki (opc.) | AppFlowy-IO/AppFlowy / outline/outline | ~60k / ~30k | AGPL / BSL | Notion-like |
| CRM | twentyhq/twenty | ~45–49k | AGPL-3.0 | CRM PostgreSQL, MCP server nativo |
| Social/Ads | gitroomhq/postiz-app | ~26–30k | AGPL-3.0 | Agendamento multi-rede, nó n8n + MCP |
| WhatsApp | EvolutionAPI/evolution-api | ~25k | Apache-2.0 | Transporte (Baileys + Cloud API), eventos NATS |
| Chatbot builder | baptisteArno/typebot.io | ~9k | AGPL-3.0 | Flow builder visual (ManyChat-like) |
| Live chat | chatwoot/chatwoot | ~21k | open-core | Inbox omnicanal humano |
| BI | apache/superset | ~63–70k | Apache-2.0 | Dashboards sobre ClickHouse |
| BI (alt.) | metabase/metabase | ~40k | AGPL | UX mais simples |
| Orquestrador | n8n-io/n8n | ~50k+ | fair-code | Nós nativos Claude/OpenAI; nó do Postiz |
| Orquestrador (alt.) | activepieces/activepieces | — | MIT | Embute o builder legalmente |

Detalhe de ouro: **Postiz já tem nó de n8n, Twenty já tem MCP, Evolution já emite por NATS** → parte da "cola" é configuração, não código.

---

# PARTE I — ESPECIFICAÇÃO DE ARQUITETURA

# Project Core-Engine — Especificação Técnica de Arquitetura (EDT)

> Plataforma modular de Produtividade + Social/Ads + Mensageria/IA + CRM + BI para agências de marketing.
> Alvo: **1 instância ARM64 (OCI Ampere A1)**. Paradigma: **Event-Driven**.
> Status do documento: **fonte da verdade**. Se o código divergir disto, o código está errado ou este documento precisa de PR.

---

## 0. Leia isto antes de qualquer linha de código (Reality Check)

A versão anterior deste plano era bonita e estava **errada em quatro pontos que quebram em produção**. Corrigi aqui. Se você é júnior e só ler uma seção, leia esta.

### Correção 1 — **n8n NÃO é a espinha dorsal**
n8n é uma ferramenta de automação de workflows, não um message bus. Cada execução do n8n abre um contexto de workflow, serializa dados de execução no Postgres e tem overhead alto **por evento**. Jogar 10.000 webhooks do Meta dentro de um `SaaS_Event_Router` único no n8n não escala — é exatamente o cenário de OOM que o próprio plano temia, só que auto-infligido.

**O que é a espinha dorsal de verdade:** um event bus leve (**Redis Streams** neste estágio; NATS JetStream quando crescer) + **consumidores finos** (serviços de ~50 linhas).
**Onde o n8n entra:** como **um** consumidor entre vários, responsável pela *cola* de integração que muda toda semana (postar no Meta/TikTok, automações de CRM configuráveis pelo usuário). Ele fica fora do caminho quente (hot path) de ingestão.

```
ERRADO (plano antigo)          CERTO (este documento)
─────────────────────          ──────────────────────
Webhook ─► n8n ─► tudo          Webhook ─► ingest (Fastify/Go) ─► Redis Stream
                                                                      │
                                          ┌───────────────┬───────────┴───────────┐
                                          ▼               ▼                        ▼
                                   worker-messaging   worker-crm            n8n (cola/integrações)
```

### Correção 2 — **LLM local não cabe nesse box em produção**
OCI Ampere A1 free tier = 4 OCPU / 24 GB RAM, **sem GPU**. Rodar Ollama com um modelo 7B útil consome 5–8 GB e **satura todos os núcleos na inferência em CPU**, matando os workers de webhook na hora do pico. É o oposto do que você quer.
**Decisão:** chat/agentes via **API externa** (Anthropic / OpenAI / Groq). Ollama, se usar, **só** para um modelo de embeddings pequeno (ex.: `nomic-embed-text`, ~300 MB) para scoring/RAG. Nunca no caminho de resposta de chat.

### Correção 3 — **1 box = 1 ponto único de falha**
Você vai guardar **tokens OAuth e CRM de clientes** numa única VPS. Um disco que morre sem backup off-box apaga o negócio dos seus clientes. O plano antigo não tinha **uma linha** sobre backup. Veja §9.

### Correção 4 — detalhes de júnior que estavam no plano
- `image: ...:latest` → builds não-reprodutíveis. **Pinar versão sempre.**
- `"value": 5000.00` → **dinheiro como float é bug.** Use `bigint` em centavos.
- Senhas em texto puro no `docker-compose.yml` → use `.env`/secrets.
- `version: '3.8'` no compose → chave obsoleta no Compose v2, remova.

---

## 1. Contrato de Eventos (o coração do sistema)

Tudo no sistema fala a mesma língua: um **envelope** padronizado. Um evento mal formado é rejeitado na borda.

```jsonc
{
  "event_id": "0b9c…",          // UUID v4 — CHAVE DE IDEMPOTÊNCIA (dedupe)
  "event":    "crm.deal.won",   // namespace.entidade.acao
  "version":  1,                // versionamento do schema do payload
  "agency_id":"99c7…",          // tenant — TODO evento é multi-tenant
  "occurred_at":"2026-06-08T11:52:00Z",
  "actor":    { "type": "user|system|webhook", "id": "…" },
  "trace_id": "f1e2…",          // rastreio + anti-loop (ver §5.D)
  "hops":     0,                // contador de saltos — corta loop infinito
  "data":     { "deal_id": "12345", "value_cents": 500000, "currency": "BRL" }
}
```

Regras inegociáveis:
1. **`event_id`** é gerado por quem produz o evento e nunca reutilizado.
2. Antes de processar, o worker checa a tabela `processed_events`. Se já existe → descarta (idempotência).
3. Evento gerado por automação **herda** o `trace_id` do gatilho e faz `hops + 1`. Se `hops > 5` → descarta e loga (mata loop CRM↔Mensageria).

---

## 2. Topologia de Infraestrutura (ARM64 / OCI)

```
[Webhooks Meta/TikTok/LinkedIn]   [Frontend SPA]
            │                          │
            ▼                          ▼
      ┌───────────────────────────────────────┐
      │        Traefik (reverse proxy + TLS)   │
      └───────────────┬───────────┬───────────┘
                      │           │
              /webhooks/*     /api/*
                      │           │
                      ▼           ▼
              ┌────────────┐ ┌──────────┐
              │  ingest    │ │   api    │  (Fastify/NestJS)
              │ (Fastify)  │ │ backend  │
              └─────┬──────┘ └────┬─────┘
                    │             │
                    ▼             ▼ (publica eventos)
              ┌─────────────────────────────┐
              │   Redis  (Streams + BullMQ)  │  ◄── espinha dorsal
              └───┬───────────┬──────────┬───┘
                  │           │          │
        ┌─────────┘     ┌─────┘     ┌────┘
        ▼               ▼           ▼
  worker-messaging  worker-social  n8n (worker+webhook)  ... consumidores
        │               │           │
        └───────┬───────┴─────┬─────┘
                ▼             ▼
        ┌──────────────┐ ┌──────────────┐
        │ PostgreSQL 16│ │ ClickHouse   │
        │ (OLTP/core)  │ │ (OLAP/BI)    │
        └──────────────┘ └──────────────┘
```

### Orçamento de memória (box de 24 GB — não é negociável, é matemática)

| Serviço            | mem_limit | Observação |
|--------------------|-----------|------------|
| SO + Docker        | ~2 GB     | reservado |
| PostgreSQL 16      | 5 GB      | `shared_buffers=1536MB` |
| ClickHouse         | 4 GB      | `max_server_memory_usage` capado |
| Redis              | 1.5 GB    | `maxmemory` + `noeviction` (fila não pode perder dado) |
| Traefik            | 256 MB    | |
| ingest             | 256 MB    | |
| api backend        | 1 GB      | |
| n8n-main           | 768 MB    | só UI/scheduler |
| n8n-webhook ×1     | 512 MB    | recebe webhooks que vão pro n8n |
| n8n-worker ×3      | 768 MB ×3 | escalável |
| workers próprios   | 512 MB ×2 | messaging/social |
| **Total**          | **~19 GB**| sobra ~5 GB de folga (saudável) |

> **Não cabe** Ollama 7B aqui. Se insistir em LLM local, troque por instância paga A1 com 48–64 GB e dedique núcleos só para inferência. Em produção neste box: **LLM por API**.

---

## 3. `docker-compose.yml` (produção, ARM64, pinado, com healthcheck)

`.env` (NÃO comitar — adicione ao `.gitignore`):
```dotenv
POSTGRES_USER=core
POSTGRES_PASSWORD=<gerar: openssl rand -base64 32>
POSTGRES_DB=saas_core
REDIS_PASSWORD=<gerar>
N8N_ENCRYPTION_KEY=<gerar: openssl rand -hex 32>   # se perder, perde todas as credenciais salvas no n8n
CLICKHOUSE_PASSWORD=<gerar>
META_APP_SECRET=<do app do Meta>
META_VERIFY_TOKEN=<você escolhe>
```

`docker-compose.yml`:
```yaml
# Compose v2 — NÃO usar a chave "version:" (obsoleta)
name: core-engine

networks:
  core_net:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  n8n_data:
  clickhouse_data:

x-n8n-env: &n8n-env       # bloco reutilizável — DRY
  DB_TYPE: postgresdb
  DB_POSTGRESDB_HOST: postgres
  DB_POSTGRESDB_PORT: "5432"
  DB_POSTGRESDB_DATABASE: ${POSTGRES_DB}
  DB_POSTGRESDB_USER: ${POSTGRES_USER}
  DB_POSTGRESDB_PASSWORD: ${POSTGRES_PASSWORD}
  EXECUTIONS_MODE: queue
  QUEUE_BULL_REDIS_HOST: redis
  QUEUE_BULL_REDIS_PORT: "6379"
  QUEUE_BULL_REDIS_PASSWORD: ${REDIS_PASSWORD}
  N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}
  QUEUE_HEALTH_CHECK_ACTIVE: "true"
  GENERIC_TIMEZONE: America/Sao_Paulo

services:

  redis:
    image: redis:7.4-alpine
    restart: unless-stopped
    networks: [core_net]
    volumes: [redis_data:/data]
    command: >
      redis-server --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 1300mb --maxmemory-policy noeviction
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    mem_limit: 1536m

  postgres:
    image: postgres:16.4-alpine
    restart: unless-stopped
    networks: [core_net]
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    command: >
      postgres -c shared_buffers=1536MB -c effective_cache_size=3GB
      -c work_mem=32MB -c maintenance_work_mem=256MB -c max_connections=120
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    mem_limit: 5g

  clickhouse:
    image: clickhouse/clickhouse-server:24.8-alpine
    restart: unless-stopped
    networks: [core_net]
    environment:
      CLICKHOUSE_USER: bi
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
      CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: "1"
    volumes: [clickhouse_data:/var/lib/clickhouse]
    ulimits:
      nofile: { soft: 262144, hard: 262144 }
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8123/ping || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5
    mem_limit: 4g

  n8n-main:
    image: docker.n8n.io/n8nio/n8n:1.107.4   # PINAR — versão exata
    restart: unless-stopped
    networks: [core_net]
    ports: ["127.0.0.1:5678:5678"]            # só localhost; exponha via Traefik
    environment:
      <<: *n8n-env
      N8N_HOST: localhost
      WEBHOOK_URL: https://seu-dominio.com/
    volumes: [n8n_data:/home/node/.n8n]
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    mem_limit: 768m

  n8n-worker:
    image: docker.n8n.io/n8nio/n8n:1.107.4
    restart: unless-stopped
    networks: [core_net]
    command: worker
    environment: *n8n-env
    depends_on:
      n8n-main: { condition: service_started }
    mem_limit: 768m
    # SEM container_name → permite --scale

  n8n-webhook:
    image: docker.n8n.io/n8nio/n8n:1.107.4
    restart: unless-stopped
    networks: [core_net]
    command: webhook
    environment: *n8n-env
    depends_on:
      n8n-main: { condition: service_started }
    mem_limit: 512m
```

> O `ingest`, o `api` e os `workers` próprios (Node/Go) entram como serviços adicionais apontando para a mesma rede `core_net` e o mesmo Redis. Mantidos em repositório de aplicação, não na infra.

Subir com escala horizontal dos workers:
```bash
docker compose up -d --scale n8n-worker=3
```

---

## 4. Banco de Dados — DDL real por módulo

> Convenção: `bigint` para dinheiro (centavos), `version int` para optimistic locking, `sort_order double precision` para drag-and-drop (fractional indexing), `agency_id` em **toda** tabela (multi-tenant).

```sql
create extension if not exists pgcrypto;   -- gen_random_uuid()
create extension if not exists citext;     -- email case-insensitive
```

### Módulo A — Produtividade (ClickUp/Monday)
```sql
create table workspaces (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null,
  created_at timestamptz not null default now()
);

create table lists (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  parent_id uuid references lists(id) on delete cascade,
  name text not null,
  sort_order double precision not null default 0
);

create table items (
  id uuid primary key default gen_random_uuid(),
  list_id uuid not null references lists(id) on delete cascade,
  agency_id uuid not null,
  title text not null,
  status text not null default 'open',
  assignee_id uuid,
  due_at timestamptz,
  fields jsonb not null default '{}'::jsonb,   -- colunas dinâmicas
  sort_order double precision not null default 0,
  version int not null default 1,              -- optimistic locking
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_items_list   on items(list_id, status);
create index idx_items_fields on items using gin (fields jsonb_path_ops);
create index idx_items_due     on items(due_at) where due_at is not null;
```
> **Caveat sênior sobre JSONB:** filtros pesados em campos quentes (ex.: "Prazo", "Aprovado por") degradam mesmo com GIN. Para esses, promova a **generated columns** indexadas:
> ```sql
> alter table items add column f_due_custom date
>   generated always as ((fields->>'prazo')::date) stored;
> create index idx_items_f_due on items(f_due_custom);
> ```

### Módulo B — Social & Ads (Hootsuite)
```sql
create table social_accounts (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  client_id uuid,
  platform text not null,                 -- meta|tiktok|linkedin|youtube
  external_account_id text not null,
  access_token_enc bytea not null,        -- CRIPTOGRAFADO (pgcrypto/KMS) — nunca texto puro
  refresh_token_enc bytea,
  expires_at timestamptz,
  scopes text[] not null default '{}',
  status text not null default 'active',  -- active|disconnected|rate_limited
  updated_at timestamptz not null default now(),
  unique (platform, external_account_id)
);

create table posts_queue (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  social_account_id uuid not null references social_accounts(id),
  payload jsonb not null,                 -- legenda, urls de mídia, alvos
  scheduled_at timestamptz not null,
  status text not null default 'pending', -- pending|processing|published|failed
  attempts smallint not null default 0,
  next_attempt_at timestamptz,            -- backoff exponencial
  last_error text,
  locked_at timestamptz,
  locked_by text,
  published_at timestamptz
);
create index idx_posts_due on posts_queue(scheduled_at)
  where status = 'pending';
```

**Pegar post sem dois workers brigarem pelo mesmo (o detalhe que faltava no plano):**
```sql
update posts_queue
set status='processing', locked_at=now(), locked_by=$1, attempts=attempts+1
where id = (
  select id from posts_queue
  where status='pending'
    and scheduled_at <= now()
    and (next_attempt_at is null or next_attempt_at <= now())
  order by scheduled_at
  for update skip locked        -- ◄── chave: pula linhas já travadas
  limit 1
)
returning *;
```
Falhou? Backoff e volta pra fila (até o limite):
```sql
update posts_queue
set status = case when attempts >= 5 then 'failed' else 'pending' end,
    next_attempt_at = now() + (interval '1 minute' * power(3, attempts)),
    last_error = $2, locked_at = null, locked_by = null
where id = $1;
```

### Módulo C — Mensageria & IA (ManyChat)
```sql
create table contacts (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  full_name text,
  email citext,
  phone text,
  external_ids jsonb not null default '{}'::jsonb,  -- {instagram:"...",whatsapp:"..."}
  tags text[] not null default '{}',
  created_at timestamptz not null default now()
);

create table chat_sessions (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  contact_id uuid not null references contacts(id),
  channel text not null,                  -- whatsapp|instagram|messenger
  current_node_id text,                   -- estado na state machine do bot
  context jsonb not null default '{}'::jsonb,
  mode text not null default 'bot',       -- bot|human (live chat)
  updated_at timestamptz not null default now()
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references chat_sessions(id),
  direction text not null,                -- in|out
  body text,
  provider_msg_id text,                   -- id da mensagem no Meta
  created_at timestamptz not null default now()
);
create unique index uq_messages_provider
  on messages(provider_msg_id) where provider_msg_id is not null;  -- dedupe de webhook duplicado
```

### Módulo D — CRM (Pipedrive)
```sql
create table pipelines (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  name text not null
);

create table stages (
  id uuid primary key default gen_random_uuid(),
  pipeline_id uuid not null references pipelines(id) on delete cascade,
  name text not null,
  sort_order double precision not null default 0,
  is_won  boolean not null default false,
  is_lost boolean not null default false
);

create table deals (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  pipeline_id uuid not null references pipelines(id),
  stage_id uuid not null references stages(id),
  contact_id uuid references contacts(id),
  title text not null,
  value_cents bigint not null default 0,  -- DINHEIRO EM CENTAVOS (nunca float)
  currency char(3) not null default 'BRL',
  probability smallint not null default 0,
  sort_order double precision not null default 0,
  version int not null default 1,         -- optimistic locking
  updated_at timestamptz not null default now()
);
create index idx_deals_stage on deals(stage_id, sort_order);
```

**Mover card no Kanban com rollback (Optimistic UI de verdade):**
```sql
update deals
set stage_id=$2, sort_order=$3, version=version+1, updated_at=now()
where id=$1 and version=$4;        -- $4 = versão que o front tinha
-- 0 linhas afetadas → HTTP 409 → o front devolve o card pro lugar e alerta
```

### Idempotência (anti-loop, dedupe) — usada por todos os workers
```sql
create table processed_events (
  event_id uuid primary key,
  event_type text not null,
  processed_at timestamptz not null default now()
);
-- limpeza periódica: delete from processed_events where processed_at < now() - interval '7 days';
```

### Módulo E — BI (ClickHouse, não Postgres)
```sql
-- executar no ClickHouse
create table events_log
(
  occurred_at  DateTime64(3),
  agency_id    UUID,
  event_type   LowCardinality(String),
  entity_id    String,
  value_cents  Int64,
  meta         String          -- JSON cru
)
engine = MergeTree
partition by toYYYYMM(occurred_at)
order by (agency_id, event_type, occurred_at);
```
Inserção **em lote** (micro-batch a cada 5–10s), nunca linha a linha — ClickHouse foi feito pra inserts massivos.

---

## 5. Caminhos críticos — código real

### A. Ingest service (Fastify) — recebe webhook do Meta e SÓ enfileira
O webhook responde `200 OK` em <200 ms. Zero lógica de negócio aqui.
```js
// ingest/server.js  — Node 20+, "type":"module"
import Fastify from 'fastify';
import crypto from 'node:crypto';
import { createClient } from 'redis';

const redis = createClient({ url: process.env.REDIS_URL });
await redis.connect();
const app = Fastify({ logger: true, bodyLimit: 1_048_576 });

// precisamos do corpo CRU para validar a assinatura HMAC
app.addContentTypeParser('application/json', { parseAs: 'buffer' },
  (_req, body, done) => done(null, body));

function validMetaSignature(raw, header) {
  if (!header) return false;
  const expected = 'sha256=' + crypto
    .createHmac('sha256', process.env.META_APP_SECRET)
    .update(raw).digest('hex');
  const a = Buffer.from(header), b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

// handshake de verificação do Meta
app.get('/webhooks/meta', async (req, reply) => {
  const q = req.query;
  if (q['hub.mode'] === 'subscribe' &&
      q['hub.verify_token'] === process.env.META_VERIFY_TOKEN) {
    return reply.code(200).send(q['hub.challenge']);
  }
  return reply.code(403).send();
});

app.post('/webhooks/meta', async (req, reply) => {
  const raw = req.body; // Buffer
  if (!validMetaSignature(raw, req.headers['x-hub-signature-256'])) {
    return reply.code(401).send();
  }
  // ÚNICA responsabilidade: jogar na fila e dar ACK rápido
  await redis.xAdd('stream:webhooks.meta', '*', { payload: raw.toString('utf8') });
  return reply.code(200).send();
});

app.listen({ host: '0.0.0.0', port: 3000 });
```

### B. Worker de mensageria com **debounce** (consolida mensagens)
Usuário manda "Oi" / "tudo bem?" / "quero o link" em 2s → uma chamada só de LLM.
```js
// worker-messaging/index.js (trecho)
// 1) cada mensagem recebida vai pro buffer da sessão e (re)agenda um job atrasado
async function onInbound(redis, queue, sessionId, text) {
  await redis.rPush(`buf:${sessionId}`, text);
  await redis.expire(`buf:${sessionId}`, 60);
  // job com a MESMA chave: se já existe, BullMQ substitui (jobId fixo + delay)
  await queue.add('flush', { sessionId },
    { jobId: `flush:${sessionId}`, delay: 2000, removeOnComplete: true });
}

// 2) quando o job dispara (2s sem novas msgs), drena o buffer e chama o LLM UMA vez
async function flush(redis, sessionId) {
  const parts = await redis.lRange(`buf:${sessionId}`, 0, -1);
  await redis.del(`buf:${sessionId}`);
  const consolidated = parts.join('\n');
  const reply = await callLLM(sessionId, consolidated); // API externa, não Ollama
  await sendToMeta(sessionId, reply);
}
```

### C. Idempotência no consumidor (qualquer worker)
```js
async function handle(pg, ev) {
  const ins = await pg.query(
    `insert into processed_events(event_id, event_type)
     values ($1,$2) on conflict (event_id) do nothing`,
    [ev.event_id, ev.event]);
  if (ins.rowCount === 0) return;       // já processado → ignora
  if (ev.hops > 5) { logLoop(ev); return; } // anti-loop
  await route(ev);                       // processa de fato
}
```

### D. Anti-loop CRM ↔ Mensageria
Toda automação que **gera** um evento novo propaga `trace_id` e incrementa `hops`. A regra "Proposta → manda WhatsApp" e "responder WhatsApp → move pra Proposta" não loopam porque na 6ª volta o `hops > 5` corta. Combinado com `processed_events`, o mesmo evento nunca roda duas vezes.

---

## 6. Tratamento de falhas das APIs externas (o "API Hell")

| Erro | Como detectar | Ação automática |
|------|---------------|-----------------|
| `429 Too Many Requests` | status code | backoff exponencial por **conta** (não global); pausa só aquele `social_account_id` |
| `401/400` token expirado | status code | `social_accounts.status='disconnected'`; cria tarefa no Módulo A; push pro usuário refazer OAuth |
| Breaking change na API | erro de schema/parse | workflow do n8n daquela rede isolado → conserta no nó visual, sem redeploy do backend |
| Webhook duplicado do Meta | `provider_msg_id` repetido | `unique index` faz o dedupe no insert |
| Timeout da rede | exceção | re-enfileira com `next_attempt_at` |

O **rate limit é por token/conta**, então a fila precisa de chave de partição por `social_account_id` — senão 1 cliente estourado trava os outros 29.

---

## 7. CQRS — separar escrita de leitura

- **Postgres** = transações rápidas (criar tarefa, mover card). **Nunca** roda agregação de relatório aqui.
- **ClickHouse** = leitura analítica. Recebe um espelho de cada evento via micro-batch.
- O dashboard ("PowerBI interno") consome uma API fina que faz `SELECT` agregado direto no ClickHouse (responde em ms para milhões de linhas) e plota com ECharts/Tremor.
- Divergência CRM vs gráfico = sinal de batch quebrado → ver §8 (observabilidade da fila).

---

## 8. Operação do dia a dia (guia de sobrevivência)

```bash
# lag da fila — métrica nº 1 a vigiar. Se cresce mais rápido que processa → suba workers
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" XLEN stream:webhooks.meta

# subir mais workers ao vivo (sem derrubar nada)
docker compose up -d --scale n8n-worker=5

# o que cada worker está processando
docker compose logs -f n8n-worker

# saúde geral
docker compose ps
docker stats --no-stream
```
**Regra de ouro:** se o n8n parece lento, **não reinicie a VPS**. Olhe o `XLEN`/lag da fila primeiro. Lag alto = falta worker, não falta reiniciar.

---

## 9. O que o plano antigo esqueceu (e te quebraria)

### Backups (sem isto, você não tem produto)
```bash
# Postgres — dump diário, enviar para OCI Object Storage (off-box!)
pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > /backup/pg_$(date +%F).sql.gz
# ClickHouse — BACKUP nativo para disco/objeto
# Redis — AOF já ligado; copie o appendonly periodicamente
```
- WAL archiving (ou `pgbackrest`) para point-in-time recovery.
- **Teste de restauração** documentado e ensaiado. Backup não testado = não existe.

### Migrations
- Use `dbmate` ou `golang-migrate` (binário único, ARM-friendly). Migração de Postgres e ClickHouse são **separadas**. Alterou schema analítico no Postgres? O nó de inserção do ClickHouse no n8n precisa refletir — não é automático.

### Segredos
- `.env` fora do git; idealmente **OCI Vault** ou `docker secrets`. **Se perder a `N8N_ENCRYPTION_KEY`, perde todos os tokens OAuth salvos no n8n.** Faça backup dela em cofre.

### Observabilidade mínima (leve, cabe no box)
- **Uptime-Kuma** (tiny) para liveness dos serviços e do `/ping`.
- Alerta de **lag de fila** (cron que lê `XLEN` e avisa se > limiar).
- Logs de execução do n8n já vão pro Postgres.

### Concorrência de edição (Notion-like)
- Texto rico colaborativo: **Yjs/CRDT** no client + WebSocket. Salva snapshot final, não o "último que clicou ganha".

---

## 10. Roadmap honesto (sequência que não vira monstro)

| Fase | Entrega | Por quê primeiro |
|------|---------|------------------|
| **0** | Infra + CI + **backups testados** + contrato de evento + idempotência | sem fundação, o resto desmorona |
| **1** | Espinha (Redis Streams + 1 worker) + Módulo A (Workspace) + Módulo D (CRM) | prova a coluna vertebral com dois módulos reais conversando |
| **2** | Módulo B (Social/Ads) com `SKIP LOCKED` + backoff + OAuth | a parte de "API Hell"; isolada por conta |
| **3** | Módulo C (Mensageria) com debounce + IA por API + state machine | depende da fila madura da fase 2 |
| **4** | Módulo E (BI) — ClickHouse + dashboard | precisa de eventos reais fluindo pra ter o que medir |

**Não** comece pela engine de social media. Comece provando que um evento nasce no Workspace e cria um card no CRM através da fila. Se isso funcionar com idempotência e sem loop, o resto são plugs.

---

## Apêndice — Tabela de riscos por módulo

| Módulo | Falha real | Mitigação implementada |
|--------|-----------|------------------------|
| Workspace | JSONB lento em filtro pesado | GIN + generated columns + paginação ≤50 |
| Workspace | edição concorrente | CRDT (Yjs) + version |
| Social | 429 / token expirado | backoff por conta + status `disconnected` + alerta |
| Social | dois workers no mesmo post | `FOR UPDATE SKIP LOCKED` |
| Mensageria | 10k webhooks simultâneos → OOM | ingest fino + Redis Stream + ACK <200ms |
| Mensageria | respostas encavaladas / custo de token | debounce 2s |
| CRM | card "salvo" mas backend falhou | optimistic locking + rollback 409 |
| CRM | loop infinito de automação | `hops>5` + `processed_events` |
| BI | deadlock no Postgres por query analítica | CQRS — leitura só no ClickHouse |
| BI | dados divergentes | micro-batch monitorado + alerta de lag |
| Infra | 1 box morre | **backup off-box testado** (a única defesa real num single-node) |

---

# PARTE II — EXTRAÇÃO & INTEGRAÇÃO OSS

# Project Core-Engine — Base de Conhecimento de Extração & Integração (OSS / GitHub)

> Companion da `ARCHITECTURE.md`. Aqui está o **como montar** o sistema reaproveitando projetos open source já validados pela comunidade, em vez de reescrever do zero.
> Princípio que rege TODO este documento: **integrar serviços, não copiar código.** Leia a §0 antes de qualquer `git clone`.

---

## 0. Princípio diretor — por que NÃO "copiar tudo pro nosso repo"

O instinto de pegar o código do Plane, do Twenty, do Postiz e colar tudo num monorepo nosso parece produtivo. Não é. É a forma mais rápida de matar o projeto, por três motivos:

1. **Upstream drift.** Cada um desses repos recebe dezenas de commits por semana. No dia em que você cola o código e começa a mexer, você criou um *fork divergente*. Seis meses depois, puxar uma correção de segurança do upstream vira um inferno de merge conflicts em código que você não escreveu e não entende.
2. **Licença.** Cinco dos sete projetos centrais são **AGPL-3.0**. Misturar o código deles dentro do *seu* código pode "contaminar" sua base inteira sob AGPL. Rodar como serviço separado, comunicando por API, **não** contamina — é a fronteira jurídica que te protege (ver §2).
3. **Manutenção.** O valor do seu produto não é re-implementar o ClickUp. É a **camada de unificação**: login único, barramento de eventos, automações entre apps, BI consolidado e a casca white-label. Isso sim você constrói.

**A regra dos três modos de uso** (toda decisão de extração cai num destes):

| Modo | Quando usar | Custo de manutenção |
|---|---|---|
| **Run-as-is** (rodar a imagem oficial, integrar por API/webhook/MCP) | Default. 90% dos casos. | Baixo — só atualizar a tag da imagem |
| **Fork cirúrgico** (forkar, mexer em 2-3 arquivos, rebasear no upstream) | Só quando precisa mudar o produto por dentro (ex.: tema white-label, remover branding) | Médio — disciplina de rebase |
| **Extrair o padrão** (não usar o código; copiar o *modelo de dados / a ideia*) | Quando o app não te serve mas a modelagem dele sim (ex.: estrutura EAV do Plane) | Zero código herdado |

Você **escreve do zero** apenas: o *Control Plane*, o *Event Spine*, a integração de SSO, a emissão de guest-tokens do BI e a casca white-label. O resto é cola.

---

## 1. Mapa mestre de repositórios

| Módulo | Repo (GitHub) | Papel no sistema | Modo de uso | Superfície de integração |
|---|---|---|---|---|
| A — Workspace | `makeplane/plane` | Tarefas, sprints, kanban, docs | **Run-as-is** | REST API + Webhooks + SDK (py/node) + MCP server (`plane-mcp-server`) |
| A — Docs (opcional) | `AppFlowy-IO/AppFlowy` ou `outline/outline` | Wiki/docs estilo Notion | Run-as-is | API / embed |
| D — CRM | `twentyhq/twenty` | Funil de vendas, contatos, objetos custom | **Run-as-is** | GraphQL + REST + Webhooks + **MCP server nativo** |
| B — Social/Ads | `gitroomhq/postiz-app` | Agendamento e publicação multi-rede | **Run-as-is** | REST API pública + **nó nativo de n8n** + MCP server |
| C — WhatsApp | `EvolutionAPI/evolution-api` | Transporte WhatsApp (Baileys + Cloud API) | **Run-as-is** | REST + Webhooks + eventos **NATS/RabbitMQ/Kafka/WebSocket** |
| C — Flow builder | `baptisteArno/typebot.io` | Construtor visual de chatbot (drag-and-drop) | **Run-as-is** + fork leve p/ branding | API + webhooks; integra nativo com Evolution |
| C — Live chat | `chatwoot/chatwoot` | Inbox omnicanal humano + bots | **Fork cirúrgico** (white-label) | API + Agent Bot API + Website widget |
| E — BI | `apache/superset` | Dashboards (o "PowerBI") sobre ClickHouse | **Run-as-is** + Embedded SDK | Embedded SDK + Guest Tokens (RLS) + driver ClickHouse |
| Espinha | `n8n-io/n8n` **ou** `activepieces/activepieces` | Orquestrador de automações entre módulos | Run-as-is (Activepieces se precisar **embutir** o builder) | Webhooks + nós + (Activepieces: MIT, embute legal) |
| Identidade | `goauthentik/authentik` ou `zitadel/zitadel` | SSO/OIDC único pra todos os apps | Run-as-is | OIDC/SAML provider |
| OLAP | ClickHouse | Data warehouse analítico | Run-as-is | SQL / HTTP |

> Os nomes de imagem Docker e tags mudam; **sempre confirme no README do repo** a tag estável atual antes de pinar. Nunca use `:latest` (ver `ARCHITECTURE.md` §0).

---

## 2. Matriz de licenças e a decisão que define a arquitetura

| Projeto | Licença | O que ela exige se você... |
|---|---|---|
| Plane, Twenty, Postiz, Typebot, Metabase | **AGPL-3.0** | ...modificar **e** servir pela rede: precisa oferecer o código modificado aos usuários. **Rodar a imagem sem modificar e integrar por API = sem obrigação de abrir nada seu.** |
| Evolution API, Superset | **Apache-2.0** | Permissiva. Pode modificar, fechar, embutir. |
| Activepieces | **MIT** | A mais permissiva. Ideal se você quer **embutir** o builder de automação dentro do seu produto. |
| n8n | **Sustainable Use License** (fair-code) | Pode self-hostar e usar internamente; **não** pode revender como SaaS concorrente do n8n hospedado. |
| Chatwoot | open-core (verifique a versão) | Edição community self-hostável; features enterprise são pagas. |

**A fronteira jurídica que organiza todo o sistema:** AGPL "pega" quando você *linka/mistura* o código no seu. Não pega quando você *fala com o app por HTTP/eventos*. Por isso o desenho é processos separados conversando por rede — não é só boa engenharia, é o que te mantém fora da obrigação de abrir seu código.

**Decisão de negócio que muda a stack:**
- **Operar para clientes da sua própria agência** (você é o operador, ninguém "recebe" o software) → AGPL é tranquila, use tudo.
- **Revender / white-label como SaaS multi-tenant para terceiros** → onde você modificar AGPL, terá obrigações. Estratégia: mantenha as modificações em apps AGPL no mínimo (só config/tema via fork cirúrgico, que é fácil de publicar) e concentre sua propriedade intelectual no Control Plane (que é **seu**, licença que você quiser).

---

## 3. O que VOCÊ constrói: a camada de unificação

Os 5 pilares abaixo são o produto de verdade. Sem eles, você tem 7 apps soltos; com eles, um ecossistema.

### 3.1 Identidade / SSO — o item nº 1 de custo de integração
Cada app tem login próprio. Sem SSO, o usuário da agência loga 7 vezes e você administra 7 bases de usuário. Solução: um **provedor OIDC central** (Authentik ou Zitadel) e cada app configurado como *client* dele.

Realidade que ninguém conta: **nem todo app suporta OIDC igual.** Antes de prometer SSO total, faça a auditoria:

| App | Suporte a OIDC/SSO | Observação |
|---|---|---|
| Twenty | OIDC/SAML (SSO é tier pago no open-core) | conferir edição |
| Plane | OIDC em algumas edições | conferir |
| Chatwoot | SAML/OIDC | ok |
| Superset | OAuth/OIDC nativo (Flask-AppBuilder) | ok, bem documentado |
| Postiz | OAuth próprio | pode exigir fork leve |
| Typebot | OAuth | conferir |
| n8n | SSO (SAML/LDAP) em tier pago | senão, acesso restrito à equipe |

Onde o app não fizer OIDC limpo, a alternativa é **provisionamento programático** (criar/sincronizar o usuário via API do app a partir do Control Plane) + acesso via proxy autenticado. Documente caso a caso.

### 3.2 Control Plane (o "cérebro" canônico) — você escreve do zero
Pequeno serviço (NestJS ou Go) que detém o **modelo canônico** e provisiona os apps. É a única fonte de verdade sobre "quem é agência, quem é cliente, quem é usuário, e qual ID isso tem em cada app".

```sql
-- banco do Control Plane (separado dos apps)
create table agencies (id uuid primary key, name text, plan text);
create table clients  (id uuid primary key, agency_id uuid, name text);
create table users    (id uuid primary key, agency_id uuid, email citext, oidc_sub text);

-- o mapa de IDs entre o nosso mundo e o mundo de cada app
create table app_entity_map (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  client_id uuid,
  app text not null,            -- plane|twenty|postiz|chatwoot|evolution|typebot
  entity_type text not null,    -- workspace|org|account|instance|inbox
  external_id text not null,    -- o ID daquele recurso DENTRO do app
  created_at timestamptz default now(),
  unique (app, entity_type, external_id)
);
```

Quando uma agência nova entra, o Control Plane orquestra o provisionamento (pseudocódigo original, ilustrativo):

```ts
async function provisionAgency(agency: Agency) {
  // cada chamada usa a API OFICIAL do app — nada de mexer no código dele
  const planeWs   = await plane.createWorkspace({ name: agency.name });
  const twentyWs  = await twenty.createWorkspace({ name: agency.name });
  const postizOrg = await postiz.createOrg({ name: agency.name });
  const cwAccount = await chatwoot.createAccount({ name: agency.name });

  await map.saveAll(agency.id, [
    ['plane','workspace', planeWs.id],
    ['twenty','workspace', twentyWs.id],
    ['postiz','org', postizOrg.id],
    ['chatwoot','account', cwAccount.id],
  ]);
  await bus.publish({ event: 'agency.provisioned', agency_id: agency.id, /* envelope §1 da bíblia */ });
}
```

Para cada **cliente** da agência que tem WhatsApp, o Control Plane cria uma **instância no Evolution API** (um número = uma instância) e guarda o `external_id`.

### 3.3 Event Spine — como cada app entra no barramento
O envelope é o da `ARCHITECTURE.md` §1. O trabalho de integração é **mapear o webhook de cada app para o envelope**. Cada app vira um *adapter* fino (uma rota no `ingest`, ou um workflow no n8n):

```
Plane webhook (issue.updated)      ─► adapter ─► { event:"task.updated",  ... }
Twenty webhook (deal stage change) ─► adapter ─► { event:"crm.deal.moved", ... }
Postiz webhook (post published)    ─► adapter ─► { event:"social.post.published", ... }
Evolution event (NATS: messages)   ─► adapter ─► { event:"msg.inbound", ... }
Chatwoot webhook (conversation)    ─► adapter ─► { event:"chat.assigned", ... }
```

Detalhe de ouro confirmado na pesquisa: **Postiz já tem nó nativo de n8n**, **Twenty já tem MCP server**, e **Evolution API já emite por NATS/RabbitMQ**. Ou seja, parte desses adapters não é código — é configuração no n8n/Activepieces. Você só escreve adapter à mão pro que não tiver integração pronta.

### 3.4 BI white-label — Superset embarcado por cliente
O pulo do gato do Módulo E: **não** mande o cliente pro Superset. Use o **Embedded SDK** do Superset, que gera *guest tokens* com **Row-Level Security** amarrada ao `agency_id`/`client_id`. Cada cliente vê só os dados dele, dentro do seu próprio frontend.

```ts
// seu backend pede um guest token ao Superset, com RLS por tenant
const token = await superset.post('/api/v1/security/guest_token/', {
  user: { username: user.email },
  resources: [{ type: 'dashboard', id: DASH_ID }],
  rls: [{ clause: `agency_id = '${user.agency_id}'` }]  // o cliente só enxerga o que é dele
});
// o frontend embute o dashboard com esse token (SDK do Superset)
```

Os dados que o Superset lê vêm do **ClickHouse** (driver `clickhouse-connect`), alimentado em micro-batches pelo Event Spine — exatamente o CQRS da `ARCHITECTURE.md` §7.

### 3.5 Gateway e domínios
Traefik na frente, **um subdomínio por app**, todos atrás do mesmo SSO:
```
app.suaagencia.com        → seu frontend (a casca white-label)
tasks.suaagencia.com      → Plane
crm.suaagencia.com        → Twenty
social.suaagencia.com     → Postiz
chat.suaagencia.com       → Chatwoot
bi.suaagencia.com         → Superset (ou embarcado em app.*)
flows.suaagencia.com      → n8n/Activepieces (restrito à equipe)
wa.suaagencia.com         → Evolution API (interno)
```
Resolve os choques de porta (Twenty e Chatwoot ambos default 3000) — internamente cada um na sua porta, externamente separados por host.

---

## 4. Plano de extração por módulo

Para cada módulo: **base**, **o que extrair**, **fork sim/não**, **eventos in/out**, **integrações**, **subir**.

### Módulo A — Workspace (base: `makeplane/plane`)
- **Extrair:** nada de código. Rodar a imagem. O que se aproveita é o produto inteiro (tarefas, kanban, sprints, docs) + a **modelagem EAV/custom-fields** como referência caso precise estender.
- **Fork?** Não. Branding via configuração; se exigir white-label profundo, fork cirúrgico só na camada web.
- **Eventos OUT:** `task.created/updated/moved`, `comment.created` (via webhooks do Plane).
- **Eventos IN:** Control Plane cria workspaces; n8n pode criar tarefas automaticamente (ex.: post falhou → tarefa pra equipe de tráfego).
- **Integra com:** CRM (lead vira tarefa), Social (erro de publicação vira tarefa).
- **Subir:** usar o `docker-compose` oficial do repo (eles publicam imagens prontas). Apontar pro Postgres central.

### Módulo D — CRM (base: `twentyhq/twenty`)
- **Extrair:** produto inteiro + **o MCP server nativo** (é o que liga o CRM aos agentes de IA sem você escrever ponte).
- **Fork?** Não. Objetos customizados já são configuráveis pela API/UI.
- **Eventos OUT:** `crm.deal.created/moved/won/lost`, `contact.created`.
- **Eventos IN:** lead vindo de comentário no Instagram (via Evolution/Postiz) → cria deal; mensagem no WhatsApp → atualiza contato.
- **Integra com:** Mensageria (lead↔contato), Workspace (deal ganho → tarefa de onboarding), BI (funil → ClickHouse).
- **Anti-loop:** as automações CRM↔Mensageria usam o `hops`/idempotência da bíblia §5.D.
- **Subir:** imagem `twentycrm/twenty` + Postgres + Redis. Ativar webhooks apontando pro `ingest`.

### Módulo B — Social/Ads (base: `gitroomhq/postiz-app`)
- **Extrair:** produto inteiro. Ele já resolve o "API Hell" (OAuth, filas de publicação, multi-rede) que a bíblia §6 descreve — **não reescreva isso**.
- **Fork?** Não. Tem **API pública + nó de n8n + MCP**: integre por aí.
- **Eventos OUT:** `social.post.scheduled/published/failed`, métricas de engajamento.
- **Eventos IN:** Control Plane cria org/canais; n8n agenda posts a partir do calendário do Workspace.
- **Integra com:** Workspace (calendário de conteúdo → agendamento), BI (engajamento → ClickHouse), CRM (comentário/lead → deal).
- **Atenção de infra:** Postiz usa **Temporal** internamente pra agendamento (além de Redis/Postgres). É um componente a mais de RAM no orçamento — contabilize.
- **Subir:** imagem oficial `ghcr.io/gitroomhq/postiz-app` + dependências do compose deles. Conectar contas via OAuth de cada rede (Meta/TikTok/LinkedIn/YouTube).

### Módulo C — Mensageria (tripé que já se integra nativamente)
Três peças, e a beleza é que **elas já conversam entre si de fábrica**:

1. **`EvolutionAPI/evolution-api`** = transporte WhatsApp. Apache-2.0 (permissiva). Emite eventos por NATS/RabbitMQ/WebSocket → conecta direto no Event Spine.
2. **`baptisteArno/typebot.io`** = construtor visual do bot (o "ManyChat"). Evolution tem integração nativa com Typebot — o fluxo do Typebot roda em cima do Evolution sem cola.
3. **`chatwoot/chatwoot`** = inbox humano (live chat, handoff bot→humano). Evolution também integra nativo.

- **Extrair:** os três como serviço. A **state machine** do bot é o Typebot; o **estado de sessão** (`current_node_id`, `context`) da bíblia §4-C você só precisa se construir lógica própria além do Typebot.
- **Fork?** Só **Chatwoot**, cirúrgico, para white-label (logo/cores/domínio) — é o único que o cliente final vê com a sua marca.
- **IA:** o debounce e a chamada de LLM (bíblia §5.B) ficam num **worker seu** (ou num fluxo Activepieces/n8n) que escuta os eventos do Evolution. LLM por **API externa**, não Ollama (bíblia §0, correção 2).
- **Eventos OUT:** `msg.inbound/outbound`, `chat.handoff`, `bot.flow.completed`.
- **Eventos IN:** CRM manda mensagem ao mudar estágio; campanha dispara fluxo.
- **Subir:** Evolution (`evoapicloud/evolution-api`) + Typebot (builder+viewer+MinIO) + Chatwoot, todos no Postgres/Redis central. Uma **instância Evolution por número de cliente**, provisionada pelo Control Plane.

### Módulo E — BI (base: `apache/superset` + ClickHouse)
- **Extrair:** Superset inteiro + o **Embedded SDK** + guest tokens com RLS (§3.4). Não reescreva engine de dashboard.
- **Fork?** Não. Branding via configuração + embed no seu frontend.
- **Dados:** ClickHouse alimentado pelo Event Spine em micro-batches. Superset conecta via `clickhouse-connect`.
- **Integra com:** todos — é o consumidor final dos eventos de todos os módulos.
- **Subir:** imagem `apache/superset` + Postgres (metadados) + Redis (cache) + driver ClickHouse instalado.

### Orquestrador (base: `n8n-io/n8n` ou `activepieces/activepieces`)
- **n8n** se a automação é interna da equipe (não revende o builder). Tem nós nativos de Claude/OpenAI + o nó do Postiz.
- **Activepieces (MIT)** se você quer **embutir o builder de automação no seu produto** e oferecer ao cliente — a licença MIT permite, a do n8n não.
- **Papel:** roteia eventos entre os adapters (§3.3) e roda as automações de negócio configuráveis. Modo **queue + workers** (bíblia §3) é obrigatório.

---

## 5. Topologia de deploy real (correção do "1 box de 24 GB")

A rota de integração **não cabe** num A1 free de 24 GB — são 7 apps, cada um com seu apetite. Distribua:

| Box | OCPU/RAM | Roda |
|---|---|---|
| **Box 1 — Dados** | 4 / 24 GB | PostgreSQL central, Redis, ClickHouse |
| **Box 2 — Apps de produto** | 4 / 24 GB | Plane, Twenty, Postiz (+Temporal), Chatwoot |
| **Box 3 — Mensageria + Orquestração** | 4 / 24 GB | Evolution, Typebot, n8n-main + workers, ingest, Control Plane |
| **Box 4 — BI + Edge** | 2 / 12 GB | Superset, Authentik (SSO), Traefik |

> No tier free da OCI dá pra fatiar a cota de 4 OCPU/24 GB em até 4 VMs Ampere menores — mas pra rodar tudo isto com folga, o realista é **instância A1 paga** ou 2-3 VMs. Reafirmando a §0 da bíblia: a rota "tudo num box" e a rota "integrar OSS" são mutuamente exclusivas. Escolha consciente.

Backups (bíblia §9) valem para **cada** Postgres e para o ClickHouse — off-box, testados.

---

## 6. Estratégia de repositório e CI

**Polyrepo, não monorepo.** Cada app OSS fica como está (imagem oficial); você não versiona o código deles. Seus repositórios são:

```
core-control-plane/      # SEU código: modelo canônico, provisionamento, mapa de IDs
core-event-spine/        # SEU código: ingest, adapters, workers (debounce, batch p/ ClickHouse)
core-frontend/           # SEU código: a casca white-label + embeds
core-infra/              # docker-compose / IaC, .env.example, migrations (dbmate)
core-forks/chatwoot/     # ÚNICO fork cirúrgico, rebaseado no upstream periodicamente
```

CI mínimo: lint + testes nos repos `core-*`; um job que, semanalmente, abre PR de bump das tags das imagens oficiais (Dependabot/Renovate) pra você revisar changelog antes de subir.

---

## 7. Roadmap de extração (faseado, sem virar monstro)

| Fase | Entrega | Critério de pronto |
|---|---|---|
| **0** | Box de dados + SSO (Authentik) + Control Plane vazio + Event Spine "hello world" | um evento atravessa o `ingest` → Redis → worker → ClickHouse |
| **1** | Plane + Twenty rodando, atrás do SSO, provisionados pelo Control Plane | criar agência provisiona workspace nos dois; webhook deles cai no Spine |
| **2** | Adapters Plane↔Twenty (lead→tarefa, deal ganho→onboarding) | automação atravessa idempotente e sem loop |
| **3** | Postiz integrado (nó n8n) + calendário↔agendamento | post publicado gera evento no Spine |
| **4** | Mensageria (Evolution+Typebot+Chatwoot) + worker de IA com debounce | "Oi/quero o link" consolida e responde via LLM externo |
| **5** | ClickHouse populado + Superset embarcado com RLS por cliente | cliente vê só os dados dele no seu frontend |
| **6** | Casca white-label final + onboarding self-service | agência nova entra sozinha e tudo é provisionado |

Não comece pela mensageria. Comece provando o ciclo **provisionar → evento → automação** com Plane+Twenty. Se isso roda limpo, os outros módulos são repetição do mesmo padrão.

---

## 8. Riscos de integração (os que aparecem no mundo real)

| Risco | Onde dói | Mitigação |
|---|---|---|
| **Upstream drift** | atualizar 7 apps quebra integração | pinar tags; Renovate; smoke tests dos webhooks no CI |
| **SSO incompleto** | app que não faz OIDC limpo | auditoria §3.1; provisionamento via API + proxy onde faltar |
| **Tenancy desalinhada** | "agency_id" não existe igual em todo app | Control Plane + `app_entity_map` é a única fonte de verdade |
| **AGPL em fork** | modificar AGPL e revender | manter forks mínimos; PI no Control Plane (licença sua) |
| **RAM estourada** | tudo num box | multi-box §5; mem_limit por container (bíblia §2) |
| **Webhook perdido** | app dispara, Spine estava fora | endpoints idempotentes + retry; reconciliação periódica via API dos apps |
| **Versão enterprise paga** | SSO/feature trancada no tier pago (Twenty, n8n, Chatwoot) | validar a feature na edição community ANTES de prometer ao cliente |

---

### TL;DR para o time júnior
Não cole o código deles no nosso. **Suba os apps oficiais, dê um login só (SSO), e escreva só a cola**: o Control Plane (quem é quem), o Event Spine (todo mundo fala o mesmo envelope) e a casca white-label. Postiz já fala n8n, Twenty já fala MCP, Evolution já fala NATS — metade da cola é configuração, não código.

---

# PARTE III — Inteligência Competitiva TomikCRM / Futura IA

> Atualização incorporada em 2026-06-23 a partir de payload observado do TomikCRM (Futura IA - CRM).
> O anexo raw e a versão JSON normalizada estão em `neural-base/sources/`. O documento humano
> completo está em `docs/COMPETITOR-TOMIKCRM-FUTURA-IA.md`.

## 1. Leitura central

TomikCRM/Futura IA valida, em produto real, a tese do FGOS: agência/operador precisa de CRM,
mensageria WhatsApp-first, IA, follow-ups, automação, agenda, financeiro, catálogo e BI em um
ecossistema multi-tenant. Para o FGOS, isto é **blueprint funcional**, não dependência técnica.

Regra de arquitetura preservada: cada lacuna virá como plug no barramento de eventos, com
`agency_id`, envelope canônico, idempotência, anti-loop e dinheiro em centavos.

## 2. Stack observada

- Frontend: React SPA, Vite, client-side routing, Signals (`preact/signals`), design system próprio,
  Phosphor Icons, charts, Sentry React 8.55.2, GTM customizado e Supabase Realtime/WebSockets.
- Backend: API `https://tomikcrm.onrender.com/api/v2`, Supabase PostgreSQL via PostgREST/RPC,
  Supabase Auth, Storage, edge functions, OpenAI, ElevenLabs, n8n, Stripe, Meta APIs, Telegram e
  Google Calendar.
- Tenancy: `organization_id` + `memberships`, roles `owner`, `admin`, `attendant`.

## 3. Módulos validados

| Grupo | Módulos observados |
|---|---|
| IA & Atendimento | TomikAI/Estrategista, Chat ao Vivo, Contatos/Mensageria, Follow-ups |
| Automação | Agentes de IA, Sistema de Treinamento, Base de Conhecimento/RAG |
| Comunicação | Conexões, Atendentes, Disparo WhatsApp |
| CRM | Leads Kanban, Leads Lista, Agenda, Clientes, Agendamentos Concluídos |
| Gestão | Colaboradores, Financeiro, Produtos e Serviços, Funil de Métricas |
| Suporte | FAQ & Ajuda, Notificações, Configurações |

## 4. Roadmap derivado para FGOS

1. **P0 — Fila/SLA de atendimento + atendentes:** eventos `chat.queued`, `chat.assigned`,
   `chat.sla_breached`, políticas manual/auto-captura/round-robin/híbrida.
2. **P0 — Follow-ups por silêncio e sequências:** worker observa mensagens, agenda cadências e emite
   `followup.scheduled`, `followup.executed`, `followup.cancelled`, `followup.failed`.
3. **P1 — BANT + temperatura + classificação por IA:** enriquecer `deals` com JSONB/generated
   columns sem quebrar optimistic lock do Kanban.
4. **P1 — Templates WhatsApp + broadcast:** estender a fila social/mensageria para HSM e texto livre
   por canal, com dedupe por provider id.
5. **P1 — RAG de produto por agência:** entidades `knowledge_bases`, `documents`, `chunks`,
   `training_qas`, separadas da `neural-base` de engenharia.
6. **P2 — Agenda, Clientes, Financeiro e Produtos:** fechar jornada lead → consulta → cliente →
   receita, sempre com eventos e valores em centavos.
7. **P2 — Agent Runtime visual:** builder só depois dos contratos de execução, providers e eventos
   estarem sólidos.

## 5. Entidades novas ou enriquecidas

TomikCRM observa `Lead`, `MessagingConversation`, `Contact`, `FollowUp`, `FollowUpSequenceRun`,
`AIAgent`, `KnowledgeBase`, `TrainingQA`, `Attendant`, `Channel`, `Appointment`, `Client`,
`Collaborator`, `Financial`, `Product` e `WhatsAppTemplate`. No FGOS, estas entidades devem ser
traduzidas para tabelas tenant-scoped e eventos canônicos, reaproveitando `contacts`, `messages`,
`deals`, `pipelines`, `stages`, `social_accounts` e `posts_queue` onde fizer sentido.
