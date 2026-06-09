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
| `/chat` | Mensageria: inbox de sessões + thread de mensagens + toggle bot/humano | `GET /api/chat/sessions`, `/api/chat/sessions/{id}/messages`, `PATCH .../mode` |
| `/social` | Social/Ads: contas, fila de posts, conectar conta, agendar | `GET /api/social-accounts`, `/api/posts`, `POST /api/social-accounts`, `POST /api/posts` |
| `/workspace` | Workspace: listas + itens, criar tarefa | `GET /api/workspaces`, `/api/lists`, `/api/items`, `POST /api/items` |

- **Kanban** move cards com **optimistic UI**: aplica local, chama o backend e, em **409 (conflito
  de versão)**, recarrega a verdade do servidor e avisa — o contrato de optimistic locking do CRM
  (docs/ARCHITECTURE.md §4-D).
- **Chat** alterna `mode` bot↔humano (handoff); no mobile vira single-pane (inbox → thread com voltar).
- **Social** conecta conta e agenda post (dry-run em dev).
- Telas degradam com mensagem clara quando a dependência está fora (ex.: Dashboard sem ClickHouse).

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

## Design

Console operacional cyber/hi-tech da FAT Tech: neon cyan/pink/purple sobre quase-preto, fontes
Orbitron (display) / Rajdhani (corpo) / Share Tech Mono (dados). Atmosfera com gradient mesh +
textura de grid; entrada em cascata (fade-up); responsivo de verdade (sidebar vira drawer com
hambúrguer no mobile, grids reflow, chat single-pane). CSS puro — sem framework, bundle ~63 KB gzip.

## Estado e pendências

✅ As **6 telas** (Login, Dashboard, CRM Kanban, Mensageria, Social/Ads, Workspace) compilam de
verdade (`tsc --noEmit` + `vite build`, 44 módulos) e são operáveis contra a API real, responsivas.

⚠️ Pendente: drag-and-drop real no Kanban (hoje botões ←/→); composer de envio de mensagem (hoje a
thread é leitura + toggle de modo); CRUD completo de workspaces/contas; testes de componente
(Vitest); empacotar `dist/` numa imagem/serviço; app mobile Expo reusando `src/lib`.
