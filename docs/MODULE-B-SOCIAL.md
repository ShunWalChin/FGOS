# Módulo B — Social/Ads (fase 2)

> Agendamento e publicação multi-rede (Meta/TikTok/LinkedIn/YouTube) resolvendo o "API Hell"
> descrito em [ARCHITECTURE.md](ARCHITECTURE.md) §6: rate limit por conta, tokens que expiram,
> e dois workers nunca brigando pelo mesmo post.

## Componentes

| Arquivo | Papel |
|---|---|
| `migrations/postgres/003_social_phase2.sql` | `rate_limited_until` na conta, `platform_post_id` no post, índices de claim |
| `src/core_engine/providers/social_base.py` | `ErrorKind`, `PublishResult`, `classify_status`, `plan_post_action`, `DryRunProvider` |
| `src/core_engine/providers/registry.py` | `get_provider(platform)`, `oauth_authorize_url(...)` |
| `src/core_engine/api/social.py` | contas, posts e OAuth (authorize/callback) |
| `src/core_engine/workers/social.py` | claim → publica → reage; emite eventos |
| `src/core_engine/repository.py` | cripto pgcrypto, claim com guardas, transições de conta |

## Fluxo de publicação

```text
POST /api/posts ──► posts_queue (pending)         social.post.scheduled ──► BI
                          │
        worker-social: claim_next_social_post  (FOR UPDATE OF pq SKIP LOCKED,
                          │                      pula conta disconnected/rate_limited,
                          │                      decifra token com pgp_sym_decrypt)
                          ▼
                 provider.publish(token, payload)
                          │
                 plan_post_action(result)
        ┌─────────────────┼───────────────────────────┬──────────────────┐
        ▼                 ▼                            ▼                  ▼
   ok: published    429: rate_limited           401/403: auth       4xx: invalid / 5xx: network
   platform_post_id  pausa conta (cooldown)     desconecta conta    dead-letter / backoff
   conta→active      backoff do post            + cria tarefa A     
        │                 │                            │                  │
        └─────────────────┴── emite social.* ─────────┴──────────────────┘
                                  (router espelha tudo pro BI)
```

## Segurança de token (cripto em repouso)

Tokens OAuth nunca são gravados em texto puro. No insert:

```sql
pgp_sym_encrypt(:access_token, :key)   -- key = TOKEN_ENCRYPTION_KEY
```

No claim, o worker recebe o token já decifrado (`pgp_sym_decrypt`), e só em memória. A API de
listagem (`GET /api/social-accounts`) jamais seleciona as colunas `*_enc`.

> Se perder `TOKEN_ENCRYPTION_KEY`, perde acesso a todos os tokens salvos. Guarde em cofre.

## Tratamento do "API Hell" (por `ErrorKind`)

| HTTP | ErrorKind | Conta | Post | Evento |
|---|---|---|---|---|
| 200 | NONE | →active | published (`platform_post_id`) | `social.post.published` |
| 429 | RATE_LIMITED | →rate_limited (cooldown 15min) | backoff | `social.account.rate_limited` |
| 401/403 | AUTH | →disconnected + tarefa de reconexão | backoff (espera reconectar) | `social.account.disconnected` |
| 4xx | INVALID | inalterada | dead-letter (`failed`) | `social.post.failed` |
| 5xx/timeout | NETWORK | inalterada | backoff exponencial | `social.post.failed` |

O rate limit é **por conta** (`social_account_id`): uma conta estourada não trava as outras —
o claim simplesmente pula contas com `rate_limited_until > now()`. Após o cooldown ela volta sozinha.

## OAuth

- `GET /api/oauth/{platform}/authorize?agency_id` → devolve a URL de consentimento + `state`.
- `GET /api/oauth/{platform}/callback?code&state` → troca o `code` por token (modo live) e chama
  `insert_social_account`. Com `SOCIAL_LIVE=false` (default dev), apenas ecoa o grant — o fluxo é
  inspecionável de ponta a ponta sem um app OAuth real.

## Modo dry-run vs live

`SOCIAL_LIVE=false` (default): `get_provider` devolve `DryRunProvider` para toda plataforma —
publica de mentira com um `platform_post_id` sintético determinístico. Todo o pipeline (claim →
evento → BI) roda offline, sem rede. Os adapters reais por plataforma entram no `registry.py` e são
ativados com `SOCIAL_LIVE=true` + credenciais.

## O que falta para "produção real" da fase 2

- Adapters reais (`MetaGraphProvider`, TikTok, LinkedIn, YouTube) com chamadas httpx + parsing de erro.
- Troca de token real no callback OAuth + refresh automático antes de `expires_at`.
- Reaper de posts presos em `processing` (worker que morreu no meio).
- Métricas de engajamento (leitura) → eventos → BI.

## Testes

`tests/test_social.py` cobre a lógica pura sem banco: `classify_status`, `plan_post_action`
(todas as ramificações), `DryRunProvider`, seleção do `registry` e construção da URL OAuth.
A fiação com Postgres/Redis é exercida no Docker via `worker-social` + smoke.
