# Engenharia Reversa — KB de Absorção para o FGOS

> Análise profunda de 6 sistemas SaaS de referência (marketing social + atendimento WhatsApp),
> com mapeamento das funcionalidades absorvíveis para os módulos do FGOS.
> Workspace de análise: `F:\_FGOS_RE\`. Data: 2026-06.
>
> **Princípio:** absorvemos *padrões de arquitetura e modelo de dados*, reescritos como código
> **original** no FGOS, alinhados ao runtime event-driven (envelope canônico, `agency_id` multi-tenant,
> dinheiro em centavos, idempotência por `event_id`, anti-loop por `hops`). Nada de cópia de código
> proprietário. Funcionalidades de spam/evasão em massa ficam fora de escopo por design.

---

## 0. Sumário executivo

| # | Sistema | Stack | Categoria | Profundidade RE | Maior valor p/ FGOS |
|---|---------|-------|-----------|-----------------|---------------------|
| 1 | **WhatICket v3** | Node/TS + React (fonte) | Atendimento multi-agente WhatsApp | 🟢 Profunda | Modelo **Ticket/Queue/Chatbot** → Módulo C |
| 2 | **WhatICket v4** | Node(dist) + React | idem + IA/n8n/Typebot/Campanhas | 🟢 Profunda | **QueueIntegration** (n8n/OpenAI) + **Campaign** |
| 3 | **Stackposts v8** | CodeIgniter 4 (PHP) | Agendador social multi-rede | 🟢 Profunda (schema) | **Scheduler social** (`posts`) → Módulo B |
| 4 | **WASender v3.5** | Laravel (PHP) | Bulk WhatsApp + API | 🟡 Boa | **Device/Template/Schedule/Webhook/API** |
| 5 | **Robô Postador FB** | Bundle JS minificado | Auto-post em grupos FB | 🔴 Leve | — (fora de escopo: spam) |

**Tese de integração:** os dois WhatICket são a fonte canônica para transformar o **Módulo C
(Mensageria)** do FGOS — hoje `contacts/chat_sessions/messages` — em um **inbox de atendimento
multi-agente** com roteamento por fila, árvore de chatbot e *delegação de bot* a orquestradores
externos (n8n/Typebot/OpenAI). Stackposts + WASender enriquecem o **Módulo B (Social/Ads)** com um
**agendador/fila de publicação** robusto (repost, intervalo, rotação anti-ban, biblioteca de mídia).

---

## 1. WhatICket v3 — Atendimento multi-agente (a joia)

**Stack:** backend Node + TypeScript (Sequelize/`sequelize-typescript`, Express, socket.io, Bull para
filas, Baileys para WhatsApp), 407 `.ts`. Frontend React (Material-UI, Context API). Padrão de
**services command-per-file** (`CreateService.ts`, `UpdateService.ts`, `ListService.ts`…).

### 1.1 Modelo de dados (núcleo)

```
Company (tenant) 1─┬─ User ──< UserQueue >── Queue ──< WhatsappQueue >── Whatsapp (sessão Baileys)
                   │                           │
                   ├─ Contact ─1──< Ticket >───┤  (ticket pertence a 1 fila e 1 atendente)
                   │                  │  └─ queueOptionId → QueueOption (árvore de chatbot)
                   │                  ├──< Message
                   │                  ├──< TicketTraking  (auditoria de transições)
                   │                  ├──< TicketNote     (notas internas)
                   │                  └──< TicketTag >── Tag
                   ├─ Campaign ── ContactList ──< ContactListItem
                   ├─ QuickMessage (respostas rápidas)
                   └─ Schedule (mensagem agendada avulsa)
```

**`Ticket`** (o conceito central que falta no FGOS): `status` (`pending`→`open`→`closed`), `channel`
(`whatsapp|facebook|instagram`), `unreadMessages`, `lastMessage`, `isGroup`, `chatbot` (flag),
`uuid`; FKs: `userId` (atendente), `contactId`, `whatsappId` (conexão), `queueId` (departamento),
`queueOptionId` (nó atual do bot), `companyId` (tenant). Tags N:N.

**`Queue`** (departamento): `name`, `color`, `greetingMessage`, `outOfHoursMessage`,
`schedules` (JSONB de horário de atendimento), N:N com `User` e `Whatsapp`, `HasMany QueueOption`.

**`QueueOption`** (árvore de chatbot/IVR): `title`, `message`, `option` (tecla digitada), `queueId`,
**`parentId` auto-referente** → menus aninhados. Mídia opcional por nó.

### 1.2 Padrões absorvíveis
- **Ciclo de vida de ticket** com `TicketTraking` (cada transição vira registro auditável) — casa com
  o `events_log`/BI do FGOS.
- **Roteamento por fila + atendente** (atribuição, fila de espera, transferência).
- **Chatbot como árvore de opções** persistida (não hard-coded) — editável pelo cliente.
- **Multi-sessão** (`Whatsapp` = conexão; várias por empresa; fila escolhe a conexão).
- **Horário de atendimento por fila** (`schedules` JSONB) com `outOfHoursMessage`.

---

## 2. WhatICket v4 — IA, n8n, Typebot e Campanhas

Backend compilado (`dist`), frontend completo. Adiciona, sobre o v3:

### 2.1 `QueueIntegration` — delegação de bot a orquestrador externo  ⭐
Tipos: **`typebot | dialogflow | n8n | openai`**. Campos relevantes: `name`, `urlN8N` (webhook do
n8n!), `typebotSlug`, `typebotDelayMessage`, `typebotExpires`, `typebotKeywordFinish/Restart`,
`typebotUnknownMessage`, `projectName`/`jsonContent` (Dialogflow), `prompt`/tokens (OpenAI).

**Por que importa para o FGOS:** o FGOS **já roda n8n** e tem a filosofia "n8n é a cola de
integrações, não o barramento". `QueueIntegration` é exatamente o contrato: uma **fila** pode
delegar a condução da conversa a um fluxo n8n (ou Typebot/OpenAI) via webhook, mantendo o FGOS como
dono do estado do ticket. Adotar isso conecta o Módulo C ao n8n de forma de primeira classe.

### 2.2 `Campaign` — disparo em massa com anti-ban
`message1..message5` + `confirmationMessage1..5` (**rotação de 5 variações** para reduzir padrão
detectável), `status` (`INATIVA|PROGRAMADA|EM_ANDAMENTO|CANCELADA|FINALIZADA`), `confirmation`,
`scheduledAt`, `completedAt`, `contactListId`, `whatsappId`; `HasMany CampaignShipping` (status por
destinatário). `CampaignSetting` guarda intervalos/limites. Serviços `Cancel/Restart`.

**Absorver:** o **padrão de campanha** (lista → agendamento → fila de shipping por destinatário com
status individual → rotação de mensagens → intervalos) é diretamente transponível para uma fila
Redis Streams + worker no FGOS, com `value`/contadores em BI.

### 2.3 Outras peças do v4
`Prompt` (prompts OpenAI por empresa/fila), `ContactList`/`ContactListItem` (+ `ImportContacts` CSV),
`Plan`/`Invoices`/`Subscriptions` (billing SaaS), `Announcement`, `Help`, `Chat` interno (atendentes).

---

## 3. Stackposts v8 — Agendador social multi-rede

**Stack:** CodeIgniter 4 modular (`inc/core/*`: Auth, Account_manager, Appearance, Blog_manager…),
1021 `.php`. Banco MySQL (`sp_*`, 22 tabelas). Multi-tenant por **`team`/`team_member`**.

### 3.1 Tabelas-núcleo (Módulo B do FGOS)
- **`sp_accounts`** — conta social: `social_network`, `category`, `team_id`, `login_type`, `can_post`,
  `pid` (id na rede), `token`, `proxy`, `status`, `data` (mediumtext JSON). Multi-rede: FB, IG,
  Twitter/X, LinkedIn, Pinterest, Reddit, Telegram, Tumblr, VK, YouTube, Google Business, OK.
- **`sp_account_sessions`** — `cookies`/`settings` (longtext) por rede: **posting via sessão/cookie**
  para redes sem API aberta (estratégia alternativa ao OAuth).
- **`sp_posts`** — *a fila do agendador*: `account_id`, `social_network`, `function`, `api_type`,
  `type`, `data` (conteúdo+mídia JSON), **`time_post`** (unix do agendamento), `delay`,
  **`repost_frequency`/`repost_until`** (repost automático), `result`, `status`. Uma linha por
  (conta × horário).
- **`sp_captions`** (biblioteca de legendas), **`sp_files`** (gerenciador de mídia com pastas),
  **`sp_groups`** (grupos de contas p/ disparo), **`sp_proxies`** (pool de proxy com limite por plano).
- **`sp_plans`** — *feature-gating* por JSON granular (`facebook_post`, `bulk_post`, `openai_content`,
  `max_storage_size`, `whatsapp_chatbot_item_limit`…). Padrão interessante de **permissões por plano**.

### 3.2 Padrões absorvíveis
- **Fila de publicação temporal** (`time_post` + `status` + `result`) → o FGOS já tem `posts_queue`
  com `SKIP LOCKED`; absorver **repost**, **delay/intervalo**, **bulk via CSV** e **biblioteca de
  mídia/legendas**.
- **Sessão/cookie + proxy** como fallback para redes sem API — útil porém com ressalvas de ToS;
  manter como estratégia *opt-in* documentada, não default.
- **Feature-gating por plano** via JSON de permissões — alinhável ao multi-tenant do FGOS (Módulo
  Acesso/Plans).

---

## 4. WASender v3.5 — Bulk WhatsApp + API + Webhooks

**Stack:** Laravel (PHP), `app/{Http,Jobs,Models,Gateway}`, 831 `.php`. Migrations revelam o domínio:
`devices` (sessões/números WhatsApp), `deviceorders`, `templates`, `schedulemessages` +
`schedulecontacts` (bulk agendado por grupo), `groups`/`groupcontacts` (segmentação), `contacts`,
`apps` (chaves de API p/ envio programático), `webhooks` (entrada), `jobs`+`failed_jobs` (fila
Laravel), `plans`/`gateways`/`orders` (billing), `permission_tables` (RBAC), `posts`/`categories`
(mini-CMS/blog).

### 4.1 Padrões absorvíveis
- **`device` = sessão WhatsApp** desacoplada do envio; **`jobs` (fila) para envio assíncrono** com
  `failed_jobs` (dead-letter) — espelha o desenho Redis Streams + `event_failures` do FGOS.
- **`templates`** reutilizáveis com variáveis; **`schedulemessages`** (agendamento) por **grupo**
  (`schedulecontacts`/`groupcontacts`).
- **`apps` + `webhooks`** — API pública para envio e recebimento (key por tenant) → padrão para
  expor o Módulo C do FGOS como API.
- **Gateways de pagamento plugáveis** (`Gateway/`) — referência para billing multi-gateway.

---

## 5. Robô Postador FB — caracterização (fora de escopo)

24 arquivos: `index.html` + `index.js`/`147.js` (webpack minificado) + fontes + `manifest.json`.
É a **casca web compilada** de um auto-postador de grupos do Facebook (provável nativefier/empacotado).
Sem código-fonte legível e com finalidade central de **postagem automatizada em massa em grupos** —
caso clássico de violação de ToS/spam. **Decisão: não absorver.** O que há de reaproveitável
(agendamento, fila) já vem, de forma legítima, do Stackposts/WASender.

---

## 6. Padrões transversais (o que todos ensinam)

1. **Multi-tenant em tudo** (`company_id`/`team_id`) — o FGOS já faz isso com `agency_id`. ✓
2. **Sessão desacoplada do envio** (Baileys `Whatsapp`/`device`) — conexão é entidade própria; o
   envio é job em fila.
3. **Fila + dead-letter para disparo** — Bull/Laravel-jobs ↔ Redis Streams/`event_failures` do FGOS.
4. **Chatbot como dado, não código** (árvore `QueueOption`) — editável pelo cliente.
5. **Delegação de bot a orquestrador externo** (`QueueIntegration` → n8n/Typebot/OpenAI) — o elo que
   liga atendimento ↔ n8n.
6. **Anti-ban por rotação** (5 variações de mensagem + intervalos) — heurística de campanha.
7. **Agendador temporal** (`time_post`/`scheduledAt` + status + result) — para social e mensageria.
8. **Feature-gating por plano** (JSON de permissões) — billing/limites por tenant.
9. **Biblioteca de mídia/legendas/templates** reutilizáveis — produtividade de conteúdo.

---

## 7. Mapa de integração → módulos FGOS

| Capacidade absorvida | Fonte | Módulo FGOS | Abordagem no FGOS | Prioridade |
|----------------------|-------|-------------|-------------------|:----------:|
| **Ticket (inbox multi-agente)** | WhatICket | C — Mensageria | Nova tabela `tickets` sobre `contacts`/`chat_sessions`; eventos `messaging.ticket.*` no barramento | **P0** |
| **Queue + atendentes** | WhatICket | C / Acesso | `queues`, `user_queues`; roteamento na entrada da mensagem | **P0** |
| **Chatbot (árvore)** | WhatICket | C | `queue_options` (auto-ref `parent_id`); avanço por `option` na state machine existente | P1 |
| **QueueIntegration → n8n/OpenAI** | WhatICket v4 | C + n8n | `queue_integrations` (`type`, `url_n8n`, `prompt`…); worker publica no webhook n8n e aguarda resposta | **P0** |
| **Campaign (bulk + anti-ban)** | WhatICket/WASender | C | `campaigns` + `campaign_shipping` (status por destinatário); worker consome fila com intervalo+rotação | P1 |
| **Templates/Quick replies** | WASender/WhatICket | C | `message_templates` (variáveis) | P2 |
| **Agendador social (repost/intervalo)** | Stackposts | B — Social | estender `posts_queue` com `time_post`, `repost_*`, `delay`; bulk CSV | P1 |
| **Biblioteca de mídia + legendas** | Stackposts | B | `media_files` (pastas) + `captions` | P2 |
| **API pública + webhooks** | WASender | C/B | chaves por agência + `webhooks` de saída | P2 |
| **Feature-gating por plano** | Stackposts/WASender | Acesso | `plans.permissions` JSONB por agência | P2 |

---

## 8. Design da integração P0 — "Atendimento" no Módulo C

Schema **original** alinhado às convenções do FGOS (Postgres, `agency_id UUID`, `*_cents bigint`,
timestamps, idempotência por evento). Reaproveita `contacts` e `chat_sessions` existentes.

```sql
-- Departamentos / filas
create table queues (
  id            uuid primary key default gen_random_uuid(),
  agency_id     uuid not null,
  name          text not null,
  color         text,
  greeting_message  text default '',
  out_of_hours_message text default '',
  schedules     jsonb default '[]'::jsonb,   -- horário de atendimento
  created_at    timestamptz not null default now()
);

-- Atendentes por fila (N:N com app_users)
create table user_queues (
  agency_id uuid not null,
  user_id   uuid not null references app_users(id),
  queue_id  uuid not null references queues(id),
  primary key (user_id, queue_id)
);

-- Tickets (conversa com ciclo de vida)
create table tickets (
  id            uuid primary key default gen_random_uuid(),
  agency_id     uuid not null,
  contact_id    uuid not null references contacts(id),
  session_id    uuid references chat_sessions(id),   -- ponte com a state machine atual
  queue_id      uuid references queues(id),
  assigned_user_id uuid references app_users(id),
  status        text not null default 'pending',     -- pending|open|closed
  channel       text not null default 'whatsapp',
  unread_count  int  not null default 0,
  last_message  text,
  is_group      boolean not null default false,
  chatbot       boolean not null default false,
  queue_option_id uuid,                               -- nó atual do bot
  rating        int,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index idx_tickets_agency_status on tickets(agency_id, status);

-- Árvore de chatbot por fila
create table queue_options (
  id         uuid primary key default gen_random_uuid(),
  agency_id  uuid not null,
  queue_id   uuid not null references queues(id),
  parent_id  uuid references queue_options(id),
  title      text,
  message    text,
  option     text,                                   -- tecla/keyword
  created_at timestamptz not null default now()
);

-- Delegação de bot a orquestrador externo (n8n/typebot/openai)
create table queue_integrations (
  id         uuid primary key default gen_random_uuid(),
  agency_id  uuid not null,
  queue_id   uuid references queues(id),
  type       text not null,                          -- typebot|n8n|openai|dialogflow
  name       text not null,
  url_n8n    text,                                   -- webhook do n8n (FGOS já roda n8n)
  prompt     text,                                   -- OpenAI
  config     jsonb default '{}'::jsonb,
  active     boolean not null default true,
  created_at timestamptz not null default now()
);
```

**Fluxo de eventos (alinhado ao barramento FGOS):**
1. Webhook de mensagem entra (Meta/WhatsApp) → `worker-messaging` resolve/cria `Contact` e `Ticket`
   (`status=pending`), publica `messaging.ticket.created` (envelope canônico, `trace_id`, `hops`).
2. Roteamento por `Queue` (greeting + horário). Se a fila tem `queue_integration` ativa → o worker
   **publica no `url_n8n`** (ou chama OpenAI) e aguarda resposta; senão percorre `queue_options`
   (árvore de chatbot) reusando a state machine do Módulo C.
3. Atribuição a atendente (`assigned_user_id`) → `messaging.ticket.assigned`. Transições →
   `messaging.ticket.updated`; fechamento → `messaging.ticket.closed`. Tudo espelhado em `events_log`
   (BI) como os demais eventos.
4. Idempotência por `event_id` (`processed_events`) e anti-loop por `hops` — já existentes.

**Frontend (SPA):** nova tela **Atendimento** (inbox): lista de tickets por status/fila, painel de
conversa, atribuir/transferir/fechar, notas internas — consumindo `/api/tickets*`.

---

## 9. Roadmap de absorção

- **Fase A (P0):** migration `008_atendimento.sql` (queues, tickets, user_queues, queue_integrations)
  + API REST `/api/queues`, `/api/tickets` + eventos `messaging.ticket.*` + tela Atendimento.
- **Fase B (P1):** `queue_options` (chatbot árvore) + `campaigns`/`campaign_shipping` (worker de
  disparo com rotação/intervalo) + scheduler social (`posts_queue` estendido: `time_post`,`repost_*`).
- **Fase C (P2):** templates/quick replies, biblioteca de mídia+legendas, API pública+webhooks,
  feature-gating por plano.

> Cada fase entra como migração versionada + serviço/worker + tela, validada por smoke E2E no
> barramento (como o `smoke_mvp` atual).
