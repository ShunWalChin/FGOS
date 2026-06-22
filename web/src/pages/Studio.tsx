import { useEffect, useState } from "react";
import {
  api,
  type Queue,
  type QueueOption,
  type QueueIntegration,
  type Template,
} from "../lib/api";
import { useAuth } from "../lib/auth";

const inp: React.CSSProperties = {
  background: "rgba(255,255,255,.04)",
  border: "1px solid rgba(255,255,255,.12)",
  borderRadius: 8,
  color: "inherit",
  padding: "8px 10px",
  font: "inherit",
  width: "100%",
};
type Tab = "chatbot" | "integracoes" | "templates";
const TABS: Array<[Tab, string]> = [
  ["chatbot", "Chatbot"],
  ["integracoes", "Integrações n8n"],
  ["templates", "Templates"],
];

export default function Studio() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [tab, setTab] = useState<Tab>("chatbot");
  const [notice, setNotice] = useState("");
  const [queues, setQueues] = useState<Queue[]>([]);

  // chatbot
  const [selQueue, setSelQueue] = useState("");
  const [options, setOptions] = useState<QueueOption[]>([]);
  const [oTitle, setOTitle] = useState("");
  const [oKey, setOKey] = useState("");
  const [oMsg, setOMsg] = useState("");
  const [qName, setQName] = useState("");

  // integrações
  const [integs, setIntegs] = useState<QueueIntegration[]>([]);
  const [iType, setIType] = useState("n8n");
  const [iName, setIName] = useState("");
  const [iQueue, setIQueue] = useState("");
  const [iUrl, setIUrl] = useState("");

  // templates
  const [templates, setTemplates] = useState<Template[]>([]);
  const [tName, setTName] = useState("");
  const [tBody, setTBody] = useState("Olá {{name}}, seu protocolo é {{protocol}}.");
  const [tShort, setTShort] = useState("");
  const [preview, setPreview] = useState("");

  async function loadQueues() {
    const qs = await api.queues(agencyId);
    setQueues(qs);
    setSelQueue((cur) => cur || (qs[0]?.id ?? ""));
  }

  useEffect(() => {
    (async () => {
      try {
        await loadQueues();
        setIntegs(await api.queueIntegrations(agencyId));
        setTemplates(await api.templates(agencyId));
      } catch (e) {
        setNotice(e instanceof Error ? e.message : "erro");
      }
    })();
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selQueue) {
      setOptions([]);
      return;
    }
    api.queueOptions(selQueue).then(setOptions).catch(() => {});
  }, [selQueue]);

  const wrap = async (fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "falha");
    }
  };

  return (
    <div>
      <div className="crumb">Studio de Atendimento · configuração do Módulo C</div>
      <h1 className="h1">Studio de Atendimento</h1>
      {notice && <div className="notice">{notice}</div>}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0 16px" }}>
        {TABS.map(([key, label]) => (
          <button
            key={key}
            className={"pill " + (tab === key ? "cyan" : "")}
            style={{ cursor: "pointer" }}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "chatbot" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Filas</b>
            <div style={{ display: "flex", gap: 8 }}>
              <input style={inp} placeholder="Nova fila…" value={qName} onChange={(e) => setQName(e.target.value)} />
              <button
                className="btn-ghost"
                onClick={() =>
                  wrap(async () => {
                    if (!qName.trim()) return;
                    await api.createQueue({ name: qName.trim() });
                    setQName("");
                    await loadQueues();
                  })
                }
              >
                + Fila
              </button>
            </div>
            <select style={inp} value={selQueue} onChange={(e) => setSelQueue(e.target.value)}>
              <option value="">Selecione a fila…</option>
              {queues.map((qq) => (
                <option key={qq.id} value={qq.id}>
                  {qq.name}
                </option>
              ))}
            </select>
            <b style={{ marginTop: 8 }}>Árvore de opções</b>
            {options.length === 0 && <div className="empty">Sem opções nesta fila.</div>}
            {options.map((o) => (
              <div key={o.id} className="mono" style={{ fontSize: 12 }}>
                <span className="pill amber">{o.option}</span> {o.title}
                <div className="muted" style={{ fontSize: 11 }}>{o.message}</div>
              </div>
            ))}
          </div>

          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Nova opção de chatbot</b>
            <input style={inp} placeholder="Tecla (ex.: 1)" value={oKey} onChange={(e) => setOKey(e.target.value)} />
            <input style={inp} placeholder="Título (ex.: Falar com vendas)" value={oTitle} onChange={(e) => setOTitle(e.target.value)} />
            <textarea style={{ ...inp, minHeight: 70 }} placeholder="Mensagem do bot" value={oMsg} onChange={(e) => setOMsg(e.target.value)} />
            <button
              className="btn-ghost"
              disabled={!selQueue}
              onClick={() =>
                wrap(async () => {
                  if (!selQueue || !oKey.trim() || !oTitle.trim()) return;
                  await api.createQueueOption(selQueue, { option: oKey.trim(), title: oTitle.trim(), message: oMsg });
                  setOKey("");
                  setOTitle("");
                  setOMsg("");
                  setOptions(await api.queueOptions(selQueue));
                })
              }
            >
              + Opção
            </button>
          </div>
        </div>
      )}

      {tab === "integracoes" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Nova integração</b>
            <select style={inp} value={iType} onChange={(e) => setIType(e.target.value)}>
              {["n8n", "openai", "typebot", "dialogflow"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input style={inp} placeholder="Nome" value={iName} onChange={(e) => setIName(e.target.value)} />
            <select style={inp} value={iQueue} onChange={(e) => setIQueue(e.target.value)}>
              <option value="">Fila (opcional)…</option>
              {queues.map((qq) => (
                <option key={qq.id} value={qq.id}>{qq.name}</option>
              ))}
            </select>
            {iType === "n8n" && (
              <input style={inp} placeholder="URL do webhook n8n" value={iUrl} onChange={(e) => setIUrl(e.target.value)} />
            )}
            <button
              className="btn-ghost"
              onClick={() =>
                wrap(async () => {
                  if (!iName.trim()) return;
                  await api.createQueueIntegration({
                    type: iType,
                    name: iName.trim(),
                    queue_id: iQueue || undefined,
                    url_n8n: iType === "n8n" ? iUrl || undefined : undefined,
                  });
                  setIName("");
                  setIUrl("");
                  setIntegs(await api.queueIntegrations(agencyId));
                })
              }
            >
              + Integração
            </button>
          </div>
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Integrações ativas</b>
            {integs.length === 0 && <div className="empty">Nenhuma integração.</div>}
            {integs.map((i) => (
              <div key={i.id} className="top">
                <span className="nm ellipsis">{i.name}</span>
                <span className={"pill " + (i.active ? "green" : "")}>{i.type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "templates" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Novo template</b>
            <input style={inp} placeholder="Nome" value={tName} onChange={(e) => setTName(e.target.value)} />
            <input style={inp} placeholder="Atalho (ex.: /oi)" value={tShort} onChange={(e) => setTShort(e.target.value)} />
            <textarea style={{ ...inp, minHeight: 90 }} value={tBody} onChange={(e) => setTBody(e.target.value)} />
            <span className="mono muted" style={{ fontSize: 11 }}>Use {"{{name}}"}, {"{{protocol}}"}…</span>
            <button
              className="btn-ghost"
              onClick={() =>
                wrap(async () => {
                  if (!tName.trim() || !tBody.trim()) return;
                  await api.createTemplate({ name: tName.trim(), body: tBody, shortcut: tShort || undefined });
                  setTName("");
                  setTShort("");
                  setTemplates(await api.templates(agencyId));
                })
              }
            >
              + Template
            </button>
          </div>
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Templates salvos</b>
            {templates.length === 0 && <div className="empty">Nenhum template.</div>}
            {templates.map((t) => (
              <div key={t.id} style={{ display: "grid", gap: 4 }}>
                <div className="top">
                  <span className="nm ellipsis">{t.name}</span>
                  {t.shortcut && <span className="pill">{t.shortcut}</span>}
                  <button
                    className="btn-ghost"
                    onClick={() =>
                      wrap(async () => {
                        const r = await api.renderTemplate(t.id, { name: "Wal", protocol: "FAT-001" });
                        setPreview(r.rendered);
                      })
                    }
                  >
                    preview
                  </button>
                </div>
                <div className="muted mono" style={{ fontSize: 11 }}>{t.body}</div>
              </div>
            ))}
            {preview && (
              <div className="notice" style={{ marginTop: 8 }}>
                <b>Preview:</b> {preview}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
