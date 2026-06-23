# Relatório de Integração — Atendimento (absorção WhatICket → FGOS)

> O que aprendemos com 6 sistemas de referência e o que **efetivamente adicionamos** ao FGOS nesta
> rodada. Companion de [REVERSE-ENGINEERING-KB.md](REVERSE-ENGINEERING-KB.md) (a base de conhecimento
> da engenharia reversa). Aqui o foco é a **entrega P0** + as 4 lentes pedidas
> (/architecture, /process-doc, /code-review, /tech-debt).

## 0. Entregue nesta rodada

| Camada | Artefato | Status |
|---|---|---|
| Conhecimento | RE profunda dos 6 sistemas + KB documentada | ✅ |
| Migração | `migrations/postgres/008_atendimento.sql` (6 tabelas) | ✅ aplicada |
| Backend | `src/core_engine/api/atendimento.py` (queues + tickets + eventos + auditoria) | ✅ no ar |
| Backend | registro do router em `api/main.py` | ✅ |
| Frontend | `web/src/pages/Atendimento.tsx` + rota + nav + client tipado | ✅ build OK |
| Validação | E2E `queue → ticket → assign → open → close+rate` + auditoria + BI | ✅ PASS |

**Absorvido (P0):** o conceito de **Ticket** (conversa com ciclo de vida), **Queue** (departamento) e
o **gancho de QueueIntegration** (delegar bot a n8n/OpenAI) — o núcleo do WhatICket — reescrito
**original** sobre o runtime event-driven do FGOS.

---

## 1. /architecture — ADR-008: Atendimento (ticketing) no Módulo C

**Contexto.** O Módulo C do FGOS tratava conversas como `chat_sessions` (state machine + debounce),
sem o conceito de *atendimento humano multi-agente*. Os sistemas WhatICket provam um modelo maduro:
`Ticket` + `Queue` + `QueueOption` + `QueueIntegration`.

**Decisão.** Introduzir `tickets` **sobre** `contacts`/`chat_sessions` (não substituir): o ticket
referencia opcionalmente a `session_id`, preservando a state machine atual como camada de bot. Toda
transição de ticket **emite evento canônico** em `stream:events` e grava `ticket_traking` (auditoria),
espelhando para o ClickHouse como os demais eventos. Multi-tenant por `agency_id`, PKs `uuid`.

**Alternativas descartadas.**
- *Estender `chat_sessions` com colunas de atendimento* — sobrecarregaria a entidade de bot e
  misturaria responsabilidades (conversa-de-bot ≠ ticket-de-atendimento).
- *Importar o schema do WhatICket as-is* (Company/Whatsapp/Bull) — traria multi-tenant e fila
  paralelos ao que o FGOS já tem; preferimos reescrever no padrão do FGOS.

**Consequências.** Ganhamos inbox multi-agente, roteamento por fila e um ponto de extensão
(`queue_integrations`) que conecta o atendimento ao **n8n que o FGOS já roda**. Débito: validação de
ownership cross-tenant na escrita (ver §3) e as fases B/C (chatbot tree, campanhas) ainda pendentes.

---

## 2. /process-doc — Fluxo do ciclo de vida do Ticket

```
                 (entrada)                          (atendimento)                 (fim)
  Webhook/Contato ──► POST /api/tickets ──► pending ──► PATCH assign ──► open ──► PATCH close ──► closed
                          │                    │            │                         │
                          ▼                    ▼            ▼                         ▼
                  emite messaging        roteado p/    assigned_user_id          rating + completedAt
                  .ticket.created        queue_id      (atendente)               (opcional)
                          │
                          └─► (se queue tem queue_integration ativa)
                                 type=n8n   → POST url_n8n (FGOS já roda n8n)
                                 type=openai→ prompt + tokens
                                 senão      → percorre queue_options (árvore de chatbot)
```

| Passo | Endpoint | Evento emitido | Auditoria (`ticket_traking`) |
|---|---|---|---|
| Abrir ticket | `POST /api/tickets` | `messaging.ticket.created` | `created` |
| Assumir/abrir | `PATCH /api/tickets/{id}` `{status:open, assigned_user_id}` | `messaging.ticket.updated` | `opened`, `assigned` |
| Mover de fila | `PATCH … {queue_id}` | `messaging.ticket.updated` | `queued` |
| Fechar | `PATCH … {status:closed}` | `messaging.ticket.updated` | `closed` |
| Avaliar | `PATCH … {rating}` | `messaging.ticket.updated` | `rated` |

Idempotência por `event_id` (`processed_events`) e anti-loop por `hops` — herdados do barramento.

---

## 3. /code-review — Revisão do código novo

**Pontos fortes**
- Segue os padrões da casa: `session_scope`, `Principal`/`get_principal`, `model_config
  extra="forbid"`, emissão via `EventEnvelope`/`bus.publish`.
- **SQL 100% parametrizado** (bind params) — sem injeção. O `where` da listagem é montado apenas de
  *fragmentos fixos* (`status`, `queue_id`), nunca de entrada crua.
- **Trilha de auditoria** (`ticket_traking`) + eventos no barramento desde o dia 0 → observабilidade/BI.

**Corrigido nesta rodada**
- 🔴→✅ **IDOR em `GET /tickets/{id}`**: não filtrava por `agency_id` (qualquer ticket por UUID).
  Adicionado `principal` + `and t.agency_id = :a`. (Coerente com a fase 7 de hardening do FGOS.)

**Achados em aberto (débito, ver §4)**
- 🟡 `create_ticket`/`update_ticket` não validam que `contact_id`/`queue_id`/`assigned_user_id`
  pertencem à mesma `agency_id` do principal (IDOR de **escrita**). Mitigação: a `agency_id` gravada
  vem sempre do principal, mas referências cruzadas não são checadas.
- 🟡 Sem máquina de estados de transição (é possível `pending → closed` direto). Aceitável para MVP.
- 🟡 `messaging.ticket.updated` pode não aparecer no BI dentro da janela de micro-batch do `worker-bi`
  no smoke (timing) — confirmar o espelhamento dos eventos de update.
- 🟡 Sem testes unitários em `tests/` para o novo módulo.

---

## 4. /tech-debt — Registro

| # | Item | Severidade | Origem | Ação proposta |
|---|---|:---:|---|---|
| D1 | Ownership cross-tenant na escrita de tickets (contact/queue/user) | Alta | esta integração | validar FK.agency_id == principal antes do insert/update |
| D2 | `redis-py` fixado só no venv (não no `pyproject`) | Alta | bring-up local | pinar `redis>=5.0,<6` no `pyproject.toml` |
| D3 | `scripts/smoke_mvp.py` desatualizado (envia `agency_id` → 422) | Média | bring-up local | remover `agency_id` do payload |
| D4 | Sem testes de `tickets`/`queues` | Média | esta integração | unittest E2E no `tests/` |
| D5 | Persistência WSL depende de keepalive manual | Média | infra local | Tarefa Agendada do Windows p/ subir WSL no logon |
| D6 | Fase B/C não implementadas (chatbot tree UI, `queue_integrations`→worker n8n, campanhas, scheduler social) | Planejado | roadmap | implementar por fases (§5) |

---

## 5. Roadmap de continuação

- **Fase B (P1):** worker que consome `messaging.ticket.created` e, se a fila tem `queue_integration`
  ativa, faz `POST url_n8n` (liga o atendimento ao n8n) ou percorre `queue_options`; tela de
  construção da **árvore de chatbot**; **Campanhas** (`campaigns`/`campaign_shipping`) com rotação de
  mensagens (anti-ban) e worker de disparo com intervalo.
- **Fase C (P2):** **scheduler social** do Stackposts (`posts_queue` + `time_post`/`repost_*`/`delay`,
  bulk CSV), biblioteca de mídia+legendas, templates/quick-replies, API pública + webhooks
  (padrão WASender), feature-gating por plano.

---

## 6. Evidência de validação

```
POST /api/queues -> 201 · POST /api/tickets -> 201
GET /api/tickets?pending -> 1 · PATCH assign+open -> 200 · PATCH close+rate -> 200
history -> [created, opened, assigned, closed, rated]
RESULT: PASS · ticket_traking: 10 linhas · BI events_log: messaging.ticket.created espelhado
Frontend: tsc --noEmit OK (45 módulos) · SPA /atendimento -> 200 (Windows)
```

**Escopo e ética.** Reescrita original (sem cópia de código proprietário). O *Robô Postador FB*
(auto-post em grupos) ficou fora por ser, na essência, ferramenta de spam/violação de ToS. As demais
capacidades absorvidas (inbox, scheduler, templates, fila) têm uso legítimo de produto.

---

## 7. Entrega da rodada profunda ("extraia tudo") — Fase B + C

Além do P0, esta rodada entregou e **validou E2E** (eventos espelhados no ClickHouse):

| Feature | Migration | Backend | Frontend | Validação |
|---|---|---|---|---|
| Campanhas (bulk + rotação anti-ban de 5 msgs) | 009 | `api/campaigns.py` + `worker-campaigns` (systemd) | `Campanhas.tsx` | 5/5 sent · started/sent/completed no BI |
| QueueIntegration → n8n/OpenAI | (008) | `atendimento.py` + `_maybe_dispatch_integration` | — | `messaging.integration.dispatched` no BI |
| Chatbot tree (`queue_options`) | (008) | `atendimento.py` (CRUD árvore auto-ref) | — | criado + listado |
| Templates / quick replies (`{{var}}`) | 010 | `atendimento.py` (`/templates/render`) | — | render PASS |
| Captions + biblioteca de mídia (pastas) | 011 | `social_extras.py` | — | pastas + arquivos PASS |
| Débitos D1/D2/D3 | — | ownership + `redis<6` + smoke fix | — | `smoke_mvp.py` PASS |

**Novo worker:** `fgos-worker-campaigns` (dry-run, mesmo padrão SKIP LOCKED + barramento).
**13 grupos de endpoints** novos (tickets, queues, queue-integrations, campaigns, contact-lists,
templates, captions, media, …). **Telas SPA:** Atendimento e Campanhas (as demais features são
API-complete, aguardando tela).

**Único item restante:** o *repost worker* do scheduler social (re-enfileirar posts publicados via
`repost_frequency/repost_until` — schema pronto na migration 011). Deixado como follow-up para não
arriscar o pipeline `worker-social` já validado.
