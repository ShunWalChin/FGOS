# FGOS — Notas do Projeto

> FAT Tech Growth Operacional System. Este documento registra **por que** o FGOS existe, **o que**
> ele consolida e **como** se relaciona com o material de origem. Para a arquitetura técnica
> completa, ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## O que é

FGOS é o repositório **principal e definitivo** de desenvolvimento da FAT Tech para o SaaS de
operação de agência de marketing. Unifica, num único ecossistema modular:

- **Produtividade** (ClickUp/Monday) — tarefas, listas, campos dinâmicos.
- **Social/Ads** (Hootsuite) — agendamento e publicação multi-rede, gestão de campanhas.
- **Mensageria + IA** (ManyChat) — chatbots, live chat omnicanal, agentes.
- **CRM** (Pipedrive) — funis Kanban, leads, scoring.
- **BI** (PowerBI) — análise consolidada de todos os módulos.

A coluna vertebral é **event-driven** (Redis Streams), não n8n. Cada módulo é um plug que escuta e
emite eventos no mesmo envelope canônico.

## Origem (a jornada até aqui)

Este projeto nasceu de uma sequência de iterações de arquitetura, condensadas nos documentos em
`docs/`:

1. **Plano inicial** — n8n como espinha dorsal + Ollama local. Bonito, mas quebrava em produção.
2. **Reality check** ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §0) — quatro correções que mudam
   o jogo: n8n não é message bus; LLM local não cabe no box; single-box precisa de backup off-box;
   dinheiro em centavos, imagens pinadas, segredos em `.env`.
3. **Runtime real** — redesenho em Python (FastAPI + Redis Streams + workers finos), que é o código
   em `src/core_engine`.
4. **FGOS** — consolidação sob a marca FAT Tech, repositório próprio, fonte única daqui pra frente.

O runtime event-driven (`src/core_engine`) é **trabalho original da FAT Tech**, escrito do zero a
partir das decisões de arquitetura consolidadas em `docs/`. Licença MIT — ver [LICENSE](LICENSE).

## O que está no repositório

```text
src/core_engine/        # runtime: envelope, bus, ingest, api (workspace/crm), workers, seed
migrations/postgres/    # schema OLTP por módulo + idempotência por worker_role
migrations/clickhouse/  # events_log (MergeTree) para BI
tests/                  # testes do envelope, segurança, messaging, router
scripts/smoke_mvp.py    # smoke end-to-end da espinha (item -> deal -> BI)
docs/                   # ARCHITECTURE (bíblia) + EXTRACTION-INTEGRATION-KB + CORE-ENGINE
neural-base/            # base de conhecimento p/ agentes de IA (graph, facts, ADRs)
docker-compose.yml      # produção single-node ARM64/OCI
```

## Duas rotas conscientes de evolução

O FGOS documenta **duas estratégias mutuamente exclusivas** de escala — escolha consciente:

- **Construir os módulos** (rota atual do `src/core_engine`): controle total, sem licença AGPL,
  cada módulo é nosso. Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Integrar OSS** (Plane + Twenty + Postiz + Evolution + Superset): muito mais rápido, mas vira
  orquestração de 7 apps com cuidado de licença AGPL e multi-box. Ver
  [docs/EXTRACTION-INTEGRATION-KB.md](docs/EXTRACTION-INTEGRATION-KB.md).

O MVP atual segue a primeira rota porque prova a espinha com código que entendemos 100%.

## Estado atual

- **Fase 0+1** ✅ — Workspace + CRM trocam eventos reais pela fila, idempotentes e sem loop, com
  espelhamento para o ClickHouse.
- **Fase 2** ✅ (estrutural) — Social/Ads: contas OAuth com token cifrado (pgcrypto), agendamento,
  `worker-social` com `SKIP LOCKED` + backoff por conta + tratamento do "API Hell" (429 pausa conta,
  401/403 desconecta + cria tarefa), provider em dry-run. Falta: adapters reais por plataforma e
  troca de token live no callback.
- **Fase 3** ✅ (estrutural) — Mensageria: debounce, state machine pura (`messaging/flow.py`), IA por
  API externa atrás de boundary (`DryRunLLM` default), envio outbound dry-run, handoff bot→humano.
  Falta: adapters HTTP reais (LLM + Meta Send) e fluxos por agência.
- **Fase 4** ✅ — BI: API de leitura sobre ClickHouse (CQRS) + dashboard ECharts em `/dashboard`.

Documentação consolidada em `docs/` (OVERVIEW, API, EVENTS, MODULE-B/C/E) e `CHANGELOG.md`.
Próximo: fase 5 (casca white-label + onboarding) ou adapters reais (LLM/social/Meta Send).

---

Desenvolvido com IA pela **FAT Tech** — Walfredo Figueiredo Neto.
