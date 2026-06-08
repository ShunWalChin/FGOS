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
