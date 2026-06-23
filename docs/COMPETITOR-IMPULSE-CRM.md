# Engenharia Reversa — Impulse CRM (concorrente)

> Análise de `crm.automatiklabs.com.br` (Impulse CRM / "Tomik"): SaaS de CRM + atendimento
> WhatsApp com IA para BPO/agências. Documento de **referência competitiva** para orientar o
> roadmap do FGOS. A primeira metade mapeia Impulse → FGOS (o que importa pra nós); a segunda
> preserva a engenharia reversa completa dos 21 módulos.
>
> Atualização 2026-06-23: a base estruturada mais completa está em
> [COMPETITOR-TOMIKCRM-FUTURA-IA.md](COMPETITOR-TOMIKCRM-FUTURA-IA.md). Este arquivo continua como
> síntese histórica; o novo documento é a fonte preferencial para entidades, endpoints e gaps.

---

## 1. Por que isto está no repositório

O Impulse é um concorrente quase 1:1 do que o FGOS quer ser nos módulos **C (Mensageria)** e
**D (CRM)**: WhatsApp-first, agentes de IA que qualificam lead via BANT, follow-up automático por
silêncio, Kanban, agenda e financeiro — tudo multi-tenant. Serve como **blueprint de funcionalidades
validadas em produção** e como mapa de lacunas do FGOS.

Stack observada do Impulse: SPA React/Next.js, multi-org isolada, Agent Runtime próprio,
integrações Meta (WABA/IG/Messenger), Telegram, Google Calendar, Vapi (Voice AI), OpenAI/Whisper.

---

## 2. Mapeamento Impulse → FGOS

| Impulse (módulo) | FGOS (módulo) | Estado no FGOS | Lacuna |
|---|---|---|---|
| TomikAI (IA estratégica sobre pipeline) | E — BI | API + dashboard | Falta **agente conversacional** sobre os dados (chat "como está meu pipeline?") |
| Chat ao Vivo (multicanal, fila, SLA) | C — Mensageria | handoff `mode=human` ✅ | Falta **fila, SLA, filtros IA/Híbrido/Humano**, UI de inbox |
| Contatos | C — Mensageria | `contacts` ✅ | UI/painel de contato |
| Follow-ups (IA / silêncio / sequências) | C + scheduler | — | **Lacuna grande**: monitor de silêncio + sequências temporais + estratégias |
| Agentes de IA (builder + runtime) | C — Mensageria | state machine + LLM ✅ | Falta **builder visual** e runtime multi-agente por organização |
| Sistema de Treinamento / RAG | (neural-base é p/ devs) | — | **RAG para agentes** (embeddings `nomic-embed`, ARCHITECTURE §0) |
| Conexões (WABA/IG/FB/Telegram) | B — Social/Ads | OAuth + token cifrado ✅ | Falta **canal WABA de mensageria** e IG/Telegram inbound |
| Atendentes (round-robin, visibilidade) | — | — | **Distribuição de conversas** (manual/round-robin/híbrido) |
| Disparo WhatsApp (templates HSM, massa) | B — Social/Ads | `posts_queue` ✅ (posts) | Falta **templates HSM** + broadcast por lista |
| Leads CRM Kanban (BANT, multi-pipeline) | D — CRM | Kanban + move 409 ✅ | Falta **BANT score**, classificação por IA, ações em massa |
| Leads Lista | D — CRM | `GET /api/deals` ✅ | Tabela rica, visões salvas, edição em massa |
| Agenda (Google Calendar) | — | — | **Módulo de agenda/calendário** |
| Clientes (lead convertido) | D — CRM | `deals`/`contacts` parcial | Entidade "cliente ativo" separada do funil |
| Agendamentos concluídos | — | — | Histórico de atendimentos |
| Colaboradores | core | `app_users` parcial | Cargos, disponibilidade/agenda |
| Financeiro (entrada/saída, fluxo de caixa) | D + E | `value_cents` parcial | **Módulo financeiro** (receitas/despesas, dashboard) |
| Produtos e Serviços | — | — | Catálogo comercial |
| Funil de Métricas | E — BI | ✅ | — (já coberto) |
| Configurações (SLA, Metas, Templates, Campos, Voice AI) | core/settings | parcial | SLA por etapa, metas, campos custom, Voice AI |
| Multi-org | core | `agency_id` multi-tenant ✅ | Seletor de org / provisionamento |

**Leitura:** FGOS já tem a **espinha** (eventos, CRM Kanban, mensageria com IA, BI) que o Impulse
expõe como produto. As maiores lacunas de produto são **Follow-ups automáticos**, **fila/SLA de
atendimento**, **distribuição de atendentes**, **agenda**, e **financeiro/produtos**.

---

## 3. Oportunidades priorizadas (candidatas a roadmap)

Ordenado por valor/esforço, reaproveitando a base event-driven do FGOS:

1. **Follow-ups por silêncio + sequências** (alto valor, médio esforço) — encaixa direto no
   barramento: um worker observa `messaging.message.inbound`/`outbound`, detecta silêncio (sem
   resposta por X tempo) e dispara uma sequência. Reusa debounce + scheduler + state machine.
2. **BANT score + classificação por IA no CRM** (alto valor, baixo esforço) — campo `bant`
   (jsonb/generated column) em `deals` + um nó de IA que sugere estágio. Reusa LLM boundary.
3. **Fila + SLA de atendimento** (alto valor, médio) — usa os SLAs por etapa (já previstos em
   ARCHITECTURE) + eventos `chat.queued`/`chat.sla_breached`; alimenta o dashboard de BI.
4. **Templates HSM + broadcast WhatsApp** (médio) — estende o Módulo B (`posts_queue` vira também
   fila de mensagens template) com aprovação Meta.
5. **Distribuição de atendentes (round-robin/híbrido)** (médio) — tabela `attendants` + política
   de atribuição no handoff.
6. **Agenda / Google Calendar** (médio) — novo módulo, integra por OAuth (reusa Módulo B) +
   eventos `appointment.*`.
7. **RAG para agentes** (médio) — embeddings pequenos (`nomic-embed-text`, ARCHITECTURE §0 correção
   2) indexando uma base por agência, consultada no nó de IA da mensageria.

> Nada disso muda a arquitetura: todos são "plugs" novos no mesmo barramento de eventos. É a tese
> central do FGOS (docs/ARCHITECTURE.md §10) validada por um concorrente real.

---

## 4. Engenharia reversa completa (referência)

### Visão geral
- **Nome:** Impulse CRM (interno: "Tomik"). **Plataforma:** SPA React/Next.js em subdomínio.
- **URL base:** `https://crm.automatiklabs.com.br/app`. **Público:** BPO, agências, times comerciais via WhatsApp.
- **Modelo:** SaaS com Trial + planos pagos. **Multi-org** com dados isolados por tenant.
- **Roteamento:** rota dedicada por módulo (`/kanban`, `/leads`, `/chat-live`, …); rota inválida → TomikAI (`/app`).

### Grupos de módulos (menu lateral)
- **IA & Atendimento:** TomikAI · Chat ao Vivo · Contatos · Follow-ups
- **Automação:** Agentes de IA · Sistema de Treinamento · Base de Conhecimento
- **Comunicação:** Conexões · Atendentes · Disparo WhatsApp
- **CRM:** Leads CRM (Kanban) · Leads Lista · Agenda · Clientes · Agendamentos Concluídos
- **Gestão:** Colaboradores · Financeiro · Produtos e Serviços · Funil de Métricas
- **Suporte:** FAQ & Ajuda · Notificações
- **Configurações:** `/settings` → Geral, SLAs, Metas, Templates, WhatsApp, Campos, Voice AI

### Módulos (resumo funcional)

**1. TomikAI** (`/app`) — chat com agentes internos (ex.: "Estrategista") que analisam pipeline,
gargalos, metas e SLAs em tempo real. Sugestões rápidas, input de texto + áudio (Whisper).

**2. Chat ao Vivo** (`/chat-live`) — inbox multicanal (WhatsApp/IG/FB/Telegram). Painel de
conversas + janela. Filtros: Todas, IA, Híbrido, Humano, Fila. Alertas de SLA na fila.

**3. Contatos** (`/conversations`) — gestão de contatos WhatsApp (via TomikHosted). Nome, telefone,
última mensagem, canal. Busca por nome/telefone/wa_id, criação, ações (chat, editar, excluir).

**4. Follow-ups** (`/follow-ups`) — automação pós-contato com IA monitorando silêncios. Sub-abas:
*Agendados por IA* (filtros por status), *Por Silêncio*, *Sequências*. KPIs: pendentes, silêncios
ativos, executados hoje, taxa 30d, falhas 7d.
- *Estratégias* (`/follow-ups/strategies`): Reengajamento Suave (3), Reativação de Lead Frio (4),
  Urgência Comercial (3, cadência 30/90/180min), Última Vaga (2), Onboarding Pós-Compra (3),
  Pós-Consulta (3), NPS + Indicação (2).
- *Analytics* (`/follow-ups/analytics`): períodos 7/30/90d, funil Agendados→Enviados→Respondidos→
  Convertidos, mapa de calor dia×hora, ranking de estratégias, export CSV.

**5. Agentes de IA** (`/agent-runtime`) — builder + runtime próprio. Sub-abas: criar, implementação
guiada, sandbox, webhooks, captura de leads, integrações de pagamento, follow-ups, atendimento,
memórias. Capacidades: resposta automática, mover lead no CRM, vendas, handoff. (Obs.: Agent Runtime
precisa de endereço público — `localhost` falha em produção.)

**6. Sistema de Treinamento** (`/training`) — Q&A e prompts por organização. Sub-abas: treinar
agente, rede neural, catálogo, migrar planilha, extrator do DNA, Q&A, gestão de prompt, gerar com
IA. Terminologia "sinapse de conhecimento".

**7. Base de Conhecimento / RAG** (`/rag`) — bases nomeadas, upload de documentos, indexação em
chunks, associação a agentes. (Ex.: base "Laura - Vendedora CRM", 1 doc, 16 chunks.)

**8. Conexões** (`/connection`) — canais: WABA oficial (recomendado), Instagram, Messenger,
Telegram, WhatsApp QR (não oficial). Sub-abas: conexão, integrações, conversões. Por canal: limite
diário, qualidade, WABA/Phone ID, ações (Manager, Números, Templates, Pagamento, Webhooks, etc.).

**9. Atendentes** (`/attendant-management`) — distribuição: Manual, Auto-captura, Round-robin,
Híbrido. Visibilidade de números: Aberto, Próprio+admin, Isolado. Limite de conversas simultâneas,
prefixo de nome, alerta de conversa sem atendente. Abas: Configurações, Desempenho, Cargos, Acesso,
Convites.

**10. Disparo WhatsApp** (`/whatsapp-templates`) — templates HSM (aprovação Meta) + envio em massa.
Por canal: Templates, Analytics.

**11. Leads CRM (Kanban)** (`/kanban`) — funil visual. Estágios (Novo/Contato/Agendamento/Consulta/
Fechado). Card: nome, valor, canal, telefone, **BANT score** (ex.: "0/4 · Frio"), tempo parado,
atendente, prioridade, destaque ⭐. Ações: abrir WhatsApp, ligar com IA (Voice AI). Métricas por
estágio, múltiplas pipelines, ações em massa, **classificação por IA** ("Classificar agora").

**12. Leads Lista** (`/leads`) — tabela: nome, contato, estágio, prioridade, criado em. Visões
salvas, modo compacto/expandido, criar/editar/excluir em massa, paginação.

**13. Agenda** (`/agenda`) — calendário integrado ao Google Calendar. Dia/Semana. Métricas: total,
realizado, agendado, IA(24h). Agendamento: horário, duração, vínculo lead/cliente, tipo. Filtro por
colaborador. Legenda por status.

**14. Clientes** (`/clients`) — leads convertidos/pagantes (separados do funil). Nome, idade,
cadastro, telefone, status. Filtros temporais, export CSV, métricas (total/ativos/mês/com email).

**15. Agendamentos Concluídos** (`/consultations`) — histórico de atendimentos realizados. Métricas:
realizados, atendidos, horas, receita. Filtros por cliente/colaborador/período/tipo.

**16. Colaboradores** (`/collaborators`) — equipe interna (realizam consultas; ≠ atendentes de
chat). Nome, cargo, email, telefone, status, disponibilidade/agenda. Recalcular stats.

**17. Financeiro** (`/financial`) — dashboard de entradas/saídas. Sub-abas: Visão Geral, Produtos.
Métricas: total entradas/saídas, saldo, transações. Fluxo de caixa, gráfico temporal, export.

**18. Produtos e Serviços** (`/products`) — catálogo. Tipos: produto/serviço/consultoria/assinatura/
curso/evento. Status: ativo/rascunho/sob demanda/fora. Grid/lista, associar a agente IA (venda
automática), migrar planilha.

**19. Funil de Métricas** (`/metrics` → redireciona para TomikAI) — métricas via agente
conversacional (Estrategista).

**20. Configurações** (`/settings`) — Geral (org, plano, equipe), **SLAs do Pipeline** (tempo máx
por etapa, alerta 80%/100%), **Metas** (faturamento/conversões/leads), **Templates** (variáveis
dinâmicas), WhatsApp (WABA), **Campos Personalizados** (7 do sistema + custom), **Voice AI** (Vapi).

**21. Organizações** — seletor multi-tenant no header; dados/canais/agentes isolados por org.

### Integrações
WABA (Meta) · Instagram Graph · Messenger · Telegram Bot · WhatsApp QR · Google Calendar · Vapi
(Voice AI) · OpenAI/Whisper (transcrição).

### Jornada do lead (fluxo principal)
1. Lead entra pelo WhatsApp → 2. Agente IA responde → 3. Capturado no Kanban (estágio "Novo") →
4. IA qualifica via BANT e move no funil → 5. Silêncio → follow-up dispara → 6. Handoff → Chat ao
Vivo → 7. Agendamento → Agenda → 8. Consulta → Agendamentos Concluídos → 9. Conversão → Clientes →
10. Financeiro registra receita.

### Modelo de dados inferido (entidades)
- **Lead:** id, nome, telefone, email, canal_origem, estágio, prioridade, valor_estimado, bant_score, atendente_id, timestamps.
- **Contato (WhatsApp):** wa_id, nome, telefone, última_mensagem, data, canal.
- **Agente de IA:** id, nome, status, etapas, canais_vinculados, memórias, created_at.
- **Follow-up:** id, lead_id, tipo (IA/silêncio/sequência), estratégia, status, horário_execução, resultado.
- **Colaborador:** id, nome, cargo, email, telefone, status, agenda_disponibilidade.
- **Agendamento:** id, lead_id, colaborador_id, horário, duração, status, tipo, fonte (IA/manual).
- **Financeiro:** id, tipo (entrada/saída), valor, produto_id, lead_id, data, created_at.

### Observações técnicas
- SPA com splash "Carregando Impulse CRM…", roteamento client-side (React).
- Auth com roles `owner`/`gerente`; multi-org com seletor no header.
- Trial: 1 agente ativo (excedido com 3).
- **Agent Runtime** próprio precisa de endpoint público (localhost falha em produção) — eco do que
  o FGOS resolve com ingest + fila (ARCHITECTURE §5).
- **Modo Essencial:** filtra a UI para Leads/Clientes/Agenda — simplificação para quem não usa o resto.
