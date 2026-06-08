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
