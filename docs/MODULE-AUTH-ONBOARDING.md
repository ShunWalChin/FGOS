# Auth + White-label & Onboarding (fase 5)

> Camada de acesso do operador: login multi-tenant (token + senha, só stdlib) e
> onboarding self-service que provisiona uma agência inteira, com branding
> white-label por tenant. É o que transforma a espinha event-driven num produto
> que "qualquer pessoa pode operar".

## Componentes

| Arquivo | Papel |
|---|---|
| `core_engine/auth.py` | JWT HS256 + hash de senha PBKDF2 — **só stdlib**, zero dependência nova, testável no host |
| `core_engine/api/deps.py` | dependency `get_principal` (Bearer → tenant) com bypass de dev |
| `core_engine/api/auth.py` | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| `core_engine/slug.py` | `slugify` + `merge_branding` (puros, testáveis) + `DEFAULT_BRANDING` |
| `core_engine/api/onboarding.py` | signup self-service, check-slug, branding público/privado |
| `onboarding/index.html` | casca white-label: página de signup temada por agência (`?org=slug`) |
| `migrations/postgres/005_auth.sql` | `password_hash` em `app_users` |
| `migrations/postgres/006_agency_whitelabel.sql` | `slug`, `plan`, `branding` em `agencies` |

## Autenticação

Stack mínima e auto-contida (sem PyJWT/passlib):

- **Senha:** `PBKDF2-HMAC-SHA256`, 200k iterações, salt aleatório por senha. Formato
  `pbkdf2_sha256$iters$salt$hash`. Comparação constant-time.
- **Token:** JWT **HS256** assinado à mão (header.payload.signature, base64url). Claims:
  `sub` (user), `agency_id` (tenant), `email`, `role`, `iat`, `exp`.
- **Dependency:** `get_principal` valida o Bearer e devolve um `Principal(user_id, agency_id, email, role)`.

### Bypass de desenvolvimento

`AUTH_REQUIRED=false` (default dev): requisição sem token cai no `DEFAULT_AGENCY_ID` — assim o
`smoke_mvp.py` e os fluxos existentes seguem funcionando sem login. Em produção
(`AUTH_REQUIRED=true`) o token passa a ser obrigatório.

### CORS

`CORSMiddleware` liberado para `CORS_ORIGINS` (default inclui `http://localhost:5173`, a porta do
web app Vite) — necessário para o frontend chamar a API de outra origem.

### Login de dev

`fgos seed` cria `dev@fgos.local` / `fgosdev` (hash PBKDF2 real, gerado em Python — nunca
hardcoded em SQL) na agência de desenvolvimento.

## Onboarding self-service

`POST /api/onboarding/signup` provisiona um tenant inteiro **numa transação**:

```
signup(agency_name, email, password, owner_name?, slug?, branding?)
  → cria agency (slug único, plan=trial, branding)
  → cria usuário owner (senha hasheada)
  → provisiona defaults: pipeline "Vendas" + stages (Lead/Proposta/Fechado) + workspace + list
  → emite evento agency.provisioned
  → devolve access_token (auto-login) + dashboard_url
```

Slug é derivado do nome (`slugify`) e garantido único (sufixo aleatório se colidir).
`GET /api/onboarding/check-slug?slug=` informa disponibilidade.

> Eco do *Control Plane* do `EXTRACTION-INTEGRATION-KB.md §3.2`: o FGOS é a fonte de verdade do
> "quem é agência, quem é owner" e provisiona os recursos do tenant.

## White-label

Cada agência tem um blob `branding` (jsonb): `display_name`, `primary_color`, `secondary_color`,
`accent_color`, `logo_url`. `merge_branding` aplica defaults FAT Tech sobre o override.

| Endpoint | Acesso | Uso |
|---|---|---|
| `GET /api/agencies/{slug}/branding` | público | a casca se tema por tenant (degrada para default se slug desconhecido) |
| `PATCH /api/agencies/branding` | autenticado | o owner edita o branding da própria agência |

A casca `onboarding/index.html` lê `?org=slug` → busca o branding público → aplica cores/logo/nome
em tempo real. É a prova visual do white-label de ponta a ponta: **um signup, temado por agência**.

## Eventos

| Evento | Produtor | `data` |
|---|---|---|
| `agency.provisioned` | API onboarding | `slug, plan, owner_email` |

(Espelhado pro BI pelo `worker-router` como qualquer evento.)

## Segurança — estado e pendências

✅ Senhas hasheadas (PBKDF2) · tokens assinados (HMAC) · comparação constant-time · CORS explícito ·
token nunca logado · `AUTH_SECRET` no `.env`/cofre.

⚠️ Pendente para produção dura: aplicar `get_principal` em **todas** as rotas de negócio derivando
`agency_id` do token (hoje os endpoints ainda aceitam `agency_id` por query/body para
compatibilidade do MVP); refresh token; rate-limit de login; rotação de `AUTH_SECRET`.

## Testes

`tests/test_auth.py` (9): roundtrip de token, segredo errado, token adulterado, expiração, senha
hash/verify, hash malformado. `tests/test_onboarding.py` (8): `slugify` (acentos, símbolos,
colapso, fallback) e `merge_branding` (defaults, override, chaves desconhecidas).
