# TomikCRM / Futura IA — Base de Conhecimento Observada

> Inteligência competitiva e blueprint funcional para o FGOS.
> Fonte observada: payload colado em 2026-06-23 sobre `crm.automatiklabs.com.br`.
> O anexo original veio truncado no campo `routes_map`; a fonte raw e a versão JSON normalizada
> estão preservadas em `neural-base/sources/`.

---

## 1. Papel deste documento

TomikCRM, também identificado como **Futura IA - CRM**, é uma plataforma SaaS multi-tenant de
atendimento, vendas, leads e automação com IA integrada. Para o FGOS, ele entra como referência de
produto validado em produção: mostra módulos, entidades, integrações e UX esperada para um CRM
WhatsApp-first com agentes.

Isto **não** muda a arquitetura do FGOS. O FGOS continua sendo FAT Tech, event-driven, com Redis
Streams como espinha, workers finos, `agency_id` em tudo, idempotência por evento e BI via
ClickHouse. O TomikCRM informa **o que construir**, não **como acoplar**.

## 2. Identidade e contexto observado

| Campo | Valor observado |
|---|---|
| Nome | TomikCRM (Futura IA - CRM) |
| Família | TomikOS (AgentOS + CRM + Operação) |
| Marca | Tomik / Automatik Labs |
| URL base | `https://crm.automatiklabs.com.br` |
| Hub | `https://crm.automatiklabs.com.br/hub` |
| Tenant observado | Futura AI Conference |
| Plano | TRIAL, expira em 2026-06-24 |
| Splash | "Carregando Futura IA - CRM..." |
| Temas | dark, light |

## 3. Stack observada

### Frontend

| Área | Evidência |
|---|---|
| Framework | React SPA |
| Bundler | Vite, assets com hash |
| Roteamento | Client-side routing |
| Estado | Signals, padrão `preact/signals` em arquivos `*-signal-*` |
| UI | Design system próprio (`CRMDesignSystemWrapper`) |
| Ícones | Phosphor Icons |
| Gráficos | `AreaChart`, `PieChart`, `PolarChart` |
| Observabilidade | Sentry React `8.55.2` |
| Analytics | GTM customizado em `gtm2.automatiklabs.com.br` |
| Tempo real | Supabase Realtime / WebSockets |

### Backend e integrações

| Área | Evidência |
|---|---|
| API | `https://tomikcrm.onrender.com/api/v2` |
| Banco | Supabase PostgreSQL via PostgREST (`/api/v2/master/rest/v1/`) |
| RPC | `/api/v2/master/rpc/` |
| Edge functions | `https://edge.automatiklabs.com.br/functions/v1/` |
| Auth | Supabase Auth, JWT e permissões por membership |
| Storage | Supabase Storage |
| Arquivos | `papaparse` para CSV, `xlsx` para Excel |
| Voice AI | ElevenLabs |
| IA | OpenAI e providers configuráveis |
| Automação | n8n via modais de conexão e seleção de workflow |
| WhatsApp oficial | WABA / Meta Cloud API |
| WhatsApp QR | `unofficial_qr` via `wa-unofficial-client` |
| Social | Instagram, Facebook Messenger, Telegram |
| Agenda | Google Calendar OAuth |
| Pagamento | Stripe |

## 4. Autenticação e tenancy

O modelo é multi-tenant por `organization_id`, com `memberships` ligando usuário e organização.
Roles observados: `owner`, `admin`, `attendant`.

Endpoints observados:

| Uso | Endpoint |
|---|---|
| Usuário logado | `GET /api/v2/users/me` |
| Permissões | `GET /api/v2/memberships/{membership_id}/permissions` |
| Garantir membro | `POST /api/v2/master/rpc/ensure_member_user` |

Tradução FGOS: `organization_id` vira `agency_id`; permissões devem sair do token/tenant do FGOS,
nunca de parâmetro livre vindo do cliente.

## 5. Inventário de módulos

### IA & Atendimento

| Item | Rota | O que valida para o FGOS |
|---|---|---|
| TomikAI (Estrategista) | `/app` | Agente conversacional sobre pipeline, metas, SLAs e prioridades |
| Chat ao Vivo | `/chat-live` | Inbox multicanal com modos IA, Híbrido, Humano, Fila e Grupos |
| Contatos / Mensageria | `/conversations` | Contato WhatsApp como entidade operacional, ligada ao lead |
| Follow-ups | `/follow-ups` | Follow-up por IA, silêncio e sequências com analytics |

### Automação

| Item | Rota | O que valida para o FGOS |
|---|---|---|
| Agentes de IA | `/agent-runtime` | Builder visual, sandbox, webhooks, captura, pagamentos, memórias |
| Sistema de Treinamento | `/training` | Q&A, prompts, catálogo, extrator de DNA e importação CSV/Excel |
| Base de Conhecimento | `/rag` | RAG por organização, bases, documentos, chunks e status |

### Comunicação

| Item | Rota | O que valida para o FGOS |
|---|---|---|
| Conexões | `/connection` | Canais WABA, WhatsApp QR, Instagram, Messenger, Telegram |
| Atendentes | `/attendant-management` | Distribuição manual, auto-captura, round-robin e híbrida |
| Disparo WhatsApp | `/whatsapp-templates` | Templates Meta e broadcast por QR/texto livre |

### CRM

| Item | Rota | O que valida para o FGOS |
|---|---|---|
| Leads CRM (Kanban) | `/kanban` | Pipeline rico com BANT, temperatura, prioridade, valor e ações |
| Leads Lista | `/leads` | Tabela com filtros, visões salvas, massa e paginação |
| Agenda | `/agenda` | Google Calendar, dia/semana, colaborador e status |
| Clientes | `/clients` | Cliente convertido separado do lead em funil |
| Agendamentos Concluídos | `/appointments-completed` | Histórico pós-atendimento |

### Gestão

| Item | Rota | O que valida para o FGOS |
|---|---|---|
| Colaboradores | `/collaborators` | Equipe operacional separada dos atendentes de chat |
| Financeiro | `/financial` | Entradas, saídas, saldo, transações e produtos |
| Produtos e Serviços | `/products` | Catálogo comercial vendido por humanos/agentes |
| Funil de Métricas | `/reports` | Relatórios executivos, SLA, no-show, velocity e receita |

### Suporte e configurações

| Item | Rota | O que valida para o FGOS |
|---|---|---|
| FAQ & Ajuda | `/faq` | Suporte operacional |
| Notificações | `/notifications` | Centro de alertas |
| Configurações | `/settings` | Geral, SLAs, metas, templates, WhatsApp, campos e Voice AI |

## 6. Contratos funcionais de maior valor

### Chat ao Vivo

Recursos observados: lista de conversas com filtros "Todos", "Minhas" e "Não atribuído"; abas
Todas, IA, Híbrido, Humano, Fila e Grupos; busca por conversa; alerta de conversas aguardando há
mais de 30 minutos; modos IA/Híbrido/Humano; botão Assumir; fila humana; atribuição de atendente;
memória ativa; composer com texto, emoji, áudio, campos, arquivo e templates.

Tradução FGOS: estender o módulo C com `chat.queued`, `chat.assigned`, `chat.handoff.changed`,
`chat.sla_breached` e uma tabela `attendants`. A UI deve ser inbox operacional, não página de
marketing.

### Follow-ups

Recursos observados: KPIs de pendentes, silêncios ativos, executados hoje, taxa de resposta em 30
dias e falhas em 7 dias; abas Agendados por IA, Por Silêncio e Sequências; submenus Fila,
Estratégias e Analytics; endpoints em `conversation_followup_tracker` e `followup_sequence_runs`.

Tradução FGOS: um worker observa mensagens inbound/outbound, agenda follow-up por silêncio e emite
eventos `followup.scheduled`, `followup.executed`, `followup.cancelled`, `followup.failed`.

### Agent Runtime

Recursos observados: criação de agentes, implementação guiada em sete passos, sandbox, webhooks,
captura de leads, pagamentos, follow-ups, atendimento e memórias persistentes. Integrações:
n8n, OpenAI, ElevenLabs, Stripe, WhatsApp e Google Calendar.

Tradução FGOS: agent runtime deve ser plugin do barramento, não o barramento. Publicação de agente
gera configuração versionada por agência; execução sempre respeita debounce, idempotência e limites.

### Treinamento e RAG

Recursos observados: Q&A por organização, prompt manager, rede neural, catálogo, migrar planilha,
extrator do DNA, base RAG com `document_count`, `chunk_count` e status.

Tradução FGOS: distinguir `neural-base/` de engenharia, que alimenta agentes de código, da base RAG
de produto por agência. Produto precisa de entidades próprias: `knowledge_bases`, `documents`,
`chunks`, `training_qas`.

### CRM Kanban e lista

Recursos observados: estágios Lead, MQL, Tentando contato, Em contato, SAL, SQL, Proposta,
Negociação, Fechado Ganho e Fechado perdido; métricas por estágio; BANT 0/4; temperatura Frio,
Morno e Quente; prioridade Baixa, Média e Alta; múltiplas pipelines; filtros por canal, período,
vendedor, destaques, pagos e convertidos; lista com 577 leads observados.

Tradução FGOS: manter `value_cents` e optimistic lock, adicionar campos de qualificação com JSONB
e generated columns para filtros quentes. Eventos de classificação devem ser separados do movimento
manual do card.

### Atendentes

Recursos observados: convite de atendente, total/online/ausente/conversas, modos de distribuição
manual, auto-captura, round-robin e híbrido; visibilidade Aberto, Próprio + admin e Isolado; limite
por atendente; nome nas mensagens; prefixo; alerta sem atendente.

Tradução FGOS: política de atribuição deve ser determinística e auditável. Distribuição e
visibilidade são regras de acesso, não apenas filtros de frontend.

### Agenda, financeiro e catálogo

Recursos observados: agenda com Google Calendar, status Agendado/Realizado/Cancelado, colaborador,
novo agendamento e conexão OAuth; financeiro com entradas, saídas, saldo e transações; produtos e
serviços com tipos Produto, Serviço, Consultoria, Assinatura, Curso e Evento.

Tradução FGOS: agenda vira módulo novo com eventos `appointment.*`; financeiro usa centavos;
catálogo alimenta CRM, agentes e relatórios de receita.

## 7. Entidades observadas

| Entidade | Tabela/campo observado | Nota para FGOS |
|---|---|---|
| Organization | `organizations`, plano, trial, contato | Equivalente a `agencies` |
| User | `users`, role, email, nome | Amarrar via token e membership |
| Membership | `memberships`, permissões | Fonte de autorização por tenant |
| Lead | `crm_leads`, estágio, prioridade, valor, BANT, temperatura | Estender `deals` sem quebrar Kanban |
| Pipeline | estágios customizáveis | Já existe no FGOS |
| MessagingConversation | `messaging_conversations`, `handoff_mode`, canal, unread | Base para inbox real |
| Contact | `contacts`, `wa_id`, `crm_lead_id` | Já existe; enriquecer sidebar |
| FollowUp | `conversation_followup_tracker` | Novo worker + scheduler |
| FollowUpSequenceRun | `followup_sequence_runs` | Cadências reutilizáveis |
| AIAgent | prompt, bases, canais, provider | Runtime versionado por agência |
| KnowledgeBase | documentos, chunks, status | RAG de produto, separado da `neural-base` |
| TrainingQA | pergunta, resposta, tags | Treinamento por organização |
| Attendant | status, conversas ativas, limite | Distribuição de atendimento |
| Channel | WABA/QR/IG/FB/Telegram | Unificar inbound/outbound |
| Appointment | cliente, colaborador, produto, status, Google event | Novo módulo Agenda |
| Client | cliente ativo/inativo | Separar lead convertido |
| Collaborator | cargo, status, stats | Profissional operacional |
| Financial | entrada/saída, valor, cliente/produto | Valores em centavos |
| Product | tipo, preço, status, imagens, estoque, tags | Catálogo comercial |
| WhatsAppTemplate | canal, nome, corpo, variáveis | Broadcast e HSM |

## 8. Endpoints observados

| Grupo | Endpoint |
|---|---|
| Auth | `GET /api/v2/users/me` |
| Auth | `GET /api/v2/memberships/{id}/permissions` |
| Auth | `POST /api/v2/master/rpc/ensure_member_user` |
| Conversas | `GET /api/v2/master/rest/v1/messaging_conversations?...handoff_mode=eq.human...assigned_user_id=is.null` |
| Presença | `GET /api/v2/attendants/presence?organization_id={id}&user_ids={...}&online_window_minutes=3` |
| Follow-ups | `GET /api/v2/master/rest/v1/conversation_followup_tracker?...status=in.(watching,cooling_down)` |
| Sequências | `GET /api/v2/master/rest/v1/followup_sequence_runs?...status=eq.active` |
| Usuários | `GET /api/v2/master/rest/v1/users?select=role&id=eq.{id}` |
| Billing | `GET /api/v2/master/rest/v1/saas_credit_auto_recharge_settings?...` |
| Edge | `POST https://edge.automatiklabs.com.br/functions/v1/track-event` |

## 9. Roadmap FGOS derivado

| Prioridade | Entrega | Motivo |
|---|---|---|
| P0 | Fila/SLA de atendimento + atendentes | Fecha a lacuna mais visível do Chat ao Vivo |
| P0 | Follow-ups por silêncio e sequências | Alto impacto comercial e encaixe natural no barramento |
| P1 | BANT + temperatura + classificação por IA | Valor alto, baixo esforço sobre `deals` |
| P1 | Templates WhatsApp e broadcast | Expande Social/Ads para mensageria outbound |
| P1 | RAG de produto por agência | Necessário para agentes vendendo com contexto |
| P2 | Agenda + Google Calendar | Completa jornada lead → consulta/agendamento |
| P2 | Clientes, financeiro e produtos | Fecha pós-venda e receita |
| P2 | Agent Runtime visual | Só depois dos contratos/eventos estarem sólidos |

## 10. Regras de implementação no FGOS

1. Todo recurso novo entra como módulo ou worker plugado em `stream:events`; nada chama outro módulo
   diretamente por HTTP.
2. Toda tabela nova tem `agency_id`, timestamps e, se mutável pela UI, `version`.
3. Todo evento novo usa envelope canônico, idempotência e anti-loop.
4. Valores financeiros usam centavos; templates e mensagens têm dedupe por provider id.
5. Integrações Meta, Google, Stripe, ElevenLabs e OpenAI ficam atrás de providers; dry-run continua
   sendo o padrão local.
6. A UI segue o padrão operacional do FGOS: densa, escaneável, com foco em execução.
