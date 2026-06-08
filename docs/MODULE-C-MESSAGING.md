# Módulo C — Mensageria & IA (fase 3)

> Chatbot omnicanal estilo ManyChat: recebe mensagens do Meta, consolida com
> **debounce**, roda uma **state machine** de conversa, cai para **IA por API
> externa** quando preciso, e faz **handoff** bot→humano. Tudo testável offline.

## Componentes

| Arquivo | Papel |
|---|---|
| `providers/meta.py` | parser defensivo do webhook Meta (channel, sender, texto, msg id) |
| `providers/llm.py` | boundary de inferência: `DryRunLLM` (default) + `AnthropicLLM` skeleton + `get_llm` |
| `providers/messenger.py` | boundary de envio (Meta Send API): `DryRunMessenger` + `get_messenger` |
| `messaging/flow.py` | `DEFAULT_FLOW` declarativo + `advance(...)` (state machine pura) |
| `workers/messaging.py` | inbound (persiste + debounce) e flusher (engine + IA + outbound) |
| `repository.py` | `upsert_contact`, `get_or_create_session`, `insert_message` (dedupe), estado/modo |
| `migrations/postgres/004_messaging_phase3.sql` | índices de lookup de sessão/mensagem |

## Fluxo

```text
webhook Meta ─► ingest ─► stream:webhooks.meta
                              │
        worker-messaging (handle_meta_message):
          upsert_contact ─► get_or_create_session ─► insert_message (dedupe)
          emite messaging.message.inbound ─► debounce buffer (chave = session_id real)
                              │  (2s sem nova msg)
        worker-messaging-flusher (flush_due_buffers ─► _respond):
          get_session ─► (mode=human? bot cala) ─► advance(DEFAULT_FLOW, node, ctx, texto)
                              │
              ┌──────────────┼───────────────────┐
              ▼              ▼                    ▼
        replies fixas    use_ai → get_llm     handoff → mode=human
              │           .complete()          + messaging.session.handoff
              ▼
        get_messenger.send() ─► insert_message(out) ─► messaging.message.outbound
        update_session_state(next_node, context)
```

## Debounce (consolidação)

Cada inbound entra num buffer Redis por sessão e (re)arma um timer (`ZADD`). O flusher só
processa quando passam `MESSAGING_DEBOUNCE_SECONDS` (2s) sem nova mensagem — então "Oi" / "tudo
bem?" / "quero o link" viram **uma** chamada de IA, não três. Reduz custo de token e evita
respostas encavaladas (docs/ARCHITECTURE.md §5.B).

## State machine (`flow.py`)

Fluxo declarativo de nós (`ask` / `say` / `ai` / `handoff`). `advance(...)` é **pura** — recebe
`(flow, current_node_id, context, user_text)` e devolve uma `Decision` (replies, próximo nó,
`use_ai`, `handoff`, atualização de contexto) sem tocar em banco ou rede. O estado vive em
`chat_sessions` (`current_node_id`, `context`, `mode`).

O `DEFAULT_FLOW` embute um fluxo de exemplo (saudação → qualificação → IA/handoff). Trocar por
fluxos por agência é só carregar outra definição (futuro: tabela `flows` ou Typebot via rota OSS).

## IA por API externa

`get_llm(settings)` devolve `DryRunLLM` por padrão. Com `MESSAGING_LLM_LIVE=true` + `LLM_API_KEY`,
devolve o adapter real (`AnthropicLLM`, ponto único de integração HTTP). A IA roda **fora do hot
path** (no flusher, após o debounce) e **nunca local no box** (docs/ARCHITECTURE.md §0 correção 2).

## Handoff bot → humano

Quando o fluxo chega a um nó `handoff`, a sessão vira `mode=human` e emite
`messaging.session.handoff`. Enquanto `mode=human`, o bot fica **silencioso** — um atendente
assume pelo live chat. Voltar para `bot` reativa a automação.

## Anti-loop / idempotência

- Webhook duplicado do Meta é descartado no `insert_message` (índice único parcial em
  `provider_msg_id`).
- O worker roda sob `worker_role="messaging"` na tabela `processed_events`.

## Dry-run vs live

| Flag | false (default) | true |
|---|---|---|
| `MESSAGING_LLM_LIVE` | `DryRunLLM` (resposta canned) | adapter real (Anthropic/OpenAI/Groq) |
| `MESSAGING_LIVE` | `DryRunMessenger` (sem rede) | Meta Send API real |

Com ambos `false`, todo o ciclo (inbound → persistência → state machine → IA → outbound → eventos)
roda offline e é exercitável no smoke/Docker sem credenciais.

## O que falta para "produção real"

- Adapter HTTP real do LLM e do Meta Send API.
- Fluxos por agência (tabela/admin) em vez do `DEFAULT_FLOW` fixo.
- Janela de contexto/histórico real enviada à IA (hoje envia a mensagem consolidada).
- Detecção de intenção mais robusta (hoje é keyword matching).

## Testes

`tests/test_messaging_flow.py`: state machine (saudação, handoff, qualificação, captura de
contexto, fallback para IA) + `DryRunLLM` + seleção segura do `get_llm`.
