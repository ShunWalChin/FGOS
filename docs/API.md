# FGOS — Referência de API

> Endpoints expostos pelo serviço `api` (FastAPI). Toda mutação publica um evento
> canônico em `stream:events` (ver [EVENTS.md](EVENTS.md)). Docs interativas em
> `http://localhost:8000/docs` quando o serviço está no ar.

Convenções:
- Autenticação: `Authorization: Bearer <token>` obtido em `/api/auth/login` ou `/api/onboarding/signup`.
  Com `AUTH_REQUIRED=false` (dev) as rotas funcionam sem token (caem na agência de dev).
- `agency_id` é multi-tenant. No MVP ainda vem no corpo/query nas rotas de negócio (hardening: derivar do token).
- Dinheiro em `value_cents` (inteiro). Datas em ISO-8601 UTC.
- Tokens de social **nunca** são retornados em respostas.

## Sistema

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | liveness do serviço |
| GET | `/api/ping` | ping simples |
| GET | `/dashboard/` | dashboard de BI (ECharts) |
| GET | `/onboarding/` | casca white-label de signup self-service |

## Auth & Onboarding (fase 5)

| Método | Rota | Corpo / Query | Evento |
|---|---|---|---|
| POST | `/api/auth/register` | `{agency_id, email, password, full_name?, role?}` | — (retorna token) |
| POST | `/api/auth/login` | `{email, password}` | — (retorna token) |
| GET | `/api/auth/me` | Bearer | — |
| POST | `/api/onboarding/signup` | `{agency_name, email, password, owner_name?, slug?, branding?}` | `agency.provisioned` |
| GET | `/api/onboarding/check-slug` | `?slug` | — |
| GET | `/api/agencies/{slug}/branding` | público | — (white-label) |
| PATCH | `/api/agencies/branding` | Bearer · `{branding}` | — |

`signup` provisiona agência + owner + pipeline/stages/workspace/list numa transação e devolve um
token de auto-login. Ver [MODULE-AUTH-ONBOARDING.md](MODULE-AUTH-ONBOARDING.md).

## Ingest (webhooks)

| Método | Rota | Descrição |
|---|---|---|
| GET | `/webhooks/meta` | handshake de verificação do Meta (`hub.challenge`) |
| POST | `/webhooks/meta` | recebe webhook, valida HMAC `x-hub-signature-256`, enfileira e dá ACK |

## Módulo A — Produtividade

| Método | Rota | Corpo / Query | Evento emitido |
|---|---|---|---|
| POST | `/api/workspaces` | `{agency_id, name}` | `workspace.created` |
| POST | `/api/lists` | `{workspace_id, name, parent_id?, sort_order?}` | — |
| POST | `/api/items` | `{list_id, agency_id, title, status?, fields?, convert_to_deal?, pipeline_id?, stage_id?, value_cents?}` | `workspace.item.created` |
| GET | `/api/items/{item_id}` | — | — |

`convert_to_deal=true` faz o `worker-router` criar um deal no CRM a partir do item.

## Módulo D — CRM

| Método | Rota | Corpo / Query | Evento emitido |
|---|---|---|---|
| POST | `/api/pipelines` | `{agency_id, name}` | — |
| POST | `/api/stages` | `{pipeline_id, name, sort_order?, is_won?, is_lost?}` | — |
| POST | `/api/deals` | `{agency_id, pipeline_id, stage_id, title, value_cents?, currency?, contact_id?, sort_order?}` | `crm.deal.created` |
| GET | `/api/deals` | `?agency_id&limit` | — |
| PATCH | `/api/deals/{deal_id}/move` | `{stage_id, sort_order, version}` | `crm.deal.moved` |

`move` usa **optimistic locking**: se `version` não bate, responde **409** (o front devolve o card).

## Módulo B — Social/Ads

| Método | Rota | Corpo / Query | Evento emitido |
|---|---|---|---|
| POST | `/api/social-accounts` | `{agency_id, platform, external_account_id, access_token, refresh_token?, scopes?, client_id?, expires_at?}` | `social.account.connected` |
| GET | `/api/social-accounts` | `?agency_id` | — (sem token) |
| POST | `/api/posts` | `{agency_id, social_account_id, caption?, media_urls?, scheduled_at}` | `social.post.scheduled` |
| GET | `/api/posts` | `?agency_id&limit` | — |
| GET | `/api/oauth/{platform}/authorize` | `?agency_id` | — (retorna `authorize_url` + `state`) |
| GET | `/api/oauth/{platform}/callback` | `?code&state` | — (dry-run se `SOCIAL_LIVE=false`) |

`platform ∈ {meta, tiktok, linkedin, youtube}`. O token é cifrado em repouso (pgcrypto)
no insert. A publicação real é feita pelo `worker-social` lendo `posts_queue`.

## Módulo E — BI (leitura só do ClickHouse)

| Método | Rota | Retorna |
|---|---|---|
| GET | `/api/bi/summary` | `?agency_id` → KPIs (eventos, tipos, valor em deals, posts, msgs) |
| GET | `/api/bi/timeseries` | `?agency_id&days` → eventos por dia |
| GET | `/api/bi/breakdown` | `?agency_id&limit` → contagem por tipo de evento |
| GET | `/api/bi/funnel` | `?agency_id` → eventos `crm.*` |
| GET | `/api/bi/health` | liveness do ClickHouse |
| GET | `/dashboard/` | dashboard ECharts (HTML estático) |

## Módulo C — Mensageria (read-API + write-path por eventos)

O **processamento** é dirigido por eventos (`POST /webhooks/meta` → workers). A **leitura** para a
UI tem endpoints REST:

| Método | Rota | Retorna |
|---|---|---|
| GET | `/api/contacts` | `?agency_id&limit` → contatos |
| GET | `/api/chat/sessions` | `?agency_id` → inbox (sessão + label do contato + última msg + modo) |
| GET | `/api/chat/sessions/{id}/messages` | thread de mensagens |
| PATCH | `/api/chat/sessions/{id}/mode` | `{mode: bot\|human}` → handoff |

## Módulo A — Produtividade (leitura)

| Método | Rota | Retorna |
|---|---|---|
| GET | `/api/workspaces` | `?agency_id` → workspaces |
| GET | `/api/lists` | `?workspace_id` → listas (com `item_count`) |
| GET | `/api/items` | `?list_id` → itens |

## Módulo D / B (leitura extra)

| Método | Rota | Retorna |
|---|---|---|
| GET | `/api/pipelines` | `?agency_id` → pipelines |
| GET | `/api/stages` | `?pipeline_id` → stages (colunas do Kanban) |

(Social já expõe `GET /api/social-accounts` e `GET /api/posts`.)

## Pendente antes de produção

- **Autenticação/autorização:** hoje a API confia no `agency_id` do payload. Antes de expor
  publicamente: middleware de auth (OIDC/JWT) + resolução `webhook → agency_id` no ingest
  (hoje cai no `DEFAULT_AGENCY_ID`).
- **Rate limit de entrada** e validação de tamanho de mídia.
