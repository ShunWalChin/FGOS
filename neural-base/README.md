# Project Core-Engine — Base Neural (Export Completo)

Export de toda a engenharia do projeto em camadas: legível por humanos, estruturada para máquina, e um índice vetorial local para busca semântica e RAG.

## Conteúdo do pacote

| Arquivo | O que é | Para quem |
|---|---|---|
| `00_MASTER_KNOWLEDGE_BASE.md` | Fonte única de verdade (arquitetura + extração OSS + pesquisa). | Humano / RAG |
| `agent_primer.md` | Versão densa para colar como contexto de agente de código. | Claude Code / Cursor |
| `knowledge_graph.json` | Grafo: módulos, repos, decisões, riscos e relações. | Tooling / IA |
| `facts.jsonl` | Fatos atômicos com metadados (unidades de embedding). | RAG |
| `decisions_adr.json` | Decisões arquiteturais registradas (ADRs). | Time / auditoria |
| `glossary.json` | Glossário de termos do projeto. | Onboarding |
| `build_vector_index.py` | Constrói o índice vetorial local (embeddings). | Engenharia |
| `query_kb.py` | Consulta semântica ao índice. | Engenharia |
| `requirements.txt` | Dependências do pipeline. | Engenharia |
| `manifest.json` | Inventário e checksums do pacote. | Versionamento |

## Três formas de usar

**1. Como memória de agente (mais rápido).**
Cole `agent_primer.md` no system/contexto do seu agente de código. Para profundidade, anexe `00_MASTER_KNOWLEDGE_BASE.md`.

**2. Como base neural pesquisável (RAG local).**
No seu box (não roda neste sandbox — o modelo é baixado na 1ª vez):
```bash
pip install -r requirements.txt
python build_vector_index.py          # gera ./vectorstore
python query_kb.py "como evitar loop de automação?"
```
O modelo `all-MiniLM-L6-v2` (~80MB) roda em CPU ARM. Depois do 1º download, tudo é offline. Os trechos retornados servem de contexto para um LLM montar a resposta final.

**3. Como dados estruturados.**
`knowledge_graph.json` e `facts.jsonl` alimentam dashboards, validações ou outro pipeline de IA. O grafo permite perguntas tipo "quais riscos o módulo de mensageria tem e o que os mitiga".

## Princípios que regem tudo (resumo de 6 linhas)
1. Espinha = Redis Streams + consumidores finos, não n8n.
2. LLM por API externa em produção.
3. Integrar OSS como serviço, nunca colar código (proteção AGPL + manutenção).
4. Você só constrói: SSO, Control Plane, Event Spine, BI embarcado, white-label.
5. Dinheiro em centavos; imagens pinadas; `agency_id` em tudo.
6. Integrar OSS exige multi-box — não cabe em 24 GB.

## Como manter o export vivo
Este é um snapshot. Ao mudar uma decisão: edite o `.md` correspondente, adicione/edite o fato em `facts.jsonl`, atualize o nó/aresta no grafo, e rode `build_vector_index.py` de novo. Versione o pacote junto com `core-infra`.
