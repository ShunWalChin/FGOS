# Web App (fase 6)

> SPA operável em React + Vite + TypeScript que consome a API do FGOS. Login →
> Dashboard (BI) → CRM Kanban. Base TypeScript pensada para compartilhar tipos e
> lógica com o app mobile (Expo/React Native) na sequência.

## Onde fica

`web/` (monorepo). Build artifacts (`node_modules/`, `dist/`) são ignorados; só o fonte é versionado.

```
web/
  package.json · vite.config.ts · tsconfig.json · index.html
  src/
    main.tsx · App.tsx · theme.css            # bootstrap, rotas, tema FAT Tech
    vite-env.d.ts
    lib/api.ts                                # client tipado + ApiError + token
    lib/auth.tsx                              # AuthProvider/useAuth (token + user no localStorage)
    components/Layout.tsx · Protected.tsx     # casca com nav + guard de rota
    pages/Login.tsx · Dashboard.tsx · Kanban.tsx
```

## Stack

- **React 18 + Vite 5 + TypeScript** (build: `tsc --noEmit && vite build`).
- **react-router-dom** para rotas; rota protegida redireciona a `/login` sem token.
- **Sem framework de CSS** — `theme.css` com a paleta FAT Tech (cyan/pink/purple, Orbitron/Rajdhani).
  Mantém o bundle leve (~57 KB gzip).

## Telas

| Rota | Tela | Consome |
|---|---|---|
| `/login` | login (dev: `dev@fgos.local`/`fgosdev`) | `POST /api/auth/login` |
| `/` | Dashboard: KPIs + breakdown de eventos | `GET /api/bi/summary`, `/api/bi/breakdown` |
| `/crm` | CRM Kanban: colunas = stages, cards = deals, mover com `version` (409), criar deal | `GET /api/pipelines`, `/api/stages`, `/api/deals`, `PATCH /api/deals/{id}/move`, `POST /api/deals` |

O Kanban move cards com **optimistic UI**: aplica local, chama o backend e, em **409 (conflito de
versão)**, recarrega a verdade do servidor e avisa — exatamente o contrato de optimistic locking do
CRM (docs/ARCHITECTURE.md §4-D). O Dashboard degrada com mensagem clara se o ClickHouse estiver fora.

## Autenticação

`lib/auth.tsx` guarda token + user no `localStorage`; `lib/api.ts` injeta `Authorization: Bearer`.
O backend aceita esse token (fase 5). Em dev com `AUTH_REQUIRED=false` o login do `fgos seed`
funciona de imediato.

## Rodar

```powershell
# backend (na VPS com Docker, ou local com venv)
fgos api            # :8000

# web app
cd web
npm install
npm run dev          # http://localhost:5173  (proxy /api -> :8000)
```

Build de produção: `npm run build` → `web/dist/` (estático; sirva por nginx/Caddy ou
FastAPI StaticFiles, apontando `/api` para o backend).

### Configuração

`VITE_API_BASE` (opcional) define a origem da API; vazio = mesma origem (proxy em dev, reverse
proxy em prod).

## Base para o mobile (próximo)

`lib/api.ts` (client + tipos) e `lib/auth.tsx` (sessão) são deliberadamente **sem dependência de
DOM** na lógica de dados — portáveis para **Expo/React Native** reusando os mesmos tipos da API.
As telas (`pages/`) são reescritas em componentes nativos; a camada de dados é compartilhada.

## Estado e pendências

✅ Compila de verdade (`tsc` + `vite build`, 41 módulos / ~57 KB gzip). Login, Dashboard e Kanban
operáveis contra a API real.

⚠️ Pendente: telas de Mensageria (chat/inbox), Social (contas/posts) e Workspace; drag-and-drop real
no Kanban (hoje botões ←/→); testes de componente (Vitest); empacotar `dist/` numa imagem/serviço.
