# FGOS — Referência de API

> Endpoints expostos pelo serviço `api` (FastAPI). Toda mutação publica um evento
> canônico em `stream:events` (ver [EVENTS.md](EVENTS.md)). Docs interativas em
> `http://localhost:8000/docs` quando o serviço está no ar.

Convenções:
- `agency_id` é obrigatório (multi-tenant). No MVP vem no corpo/query; **falta auth** (ver §final).
- Dinheiro em `value_cents` (inteiro). Datas em ISO-8601 UTC.
- Tokens de social **nunca** são retornados em respostas.

## Sistema

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | liveness do serviço |
| GET | `/api/ping` | ping simples |

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

## Pendente antes de produção

- **Autenticação/autorização:** hoje a API confia no `agency_id` do payload. Antes de expor
  publicamente: middleware de auth (OIDC/JWT) + resolução `webhook → agency_id` no ingest
  (hoje cai no `DEFAULT_AGENCY_ID`).
- **Rate limit de entrada** e validação de tamanho de mídia.
