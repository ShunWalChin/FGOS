import { useEffect, useState } from "react";
import { api, type Campaign, type ContactList } from "../lib/api";
import { useAuth } from "../lib/auth";

const statusPill: Record<string, string> = {
  draft: "",
  scheduled: "amber",
  running: "cyan",
  done: "green",
  cancelled: "pink",
};
const inp: React.CSSProperties = {
  background: "rgba(255,255,255,.04)",
  border: "1px solid rgba(255,255,255,.12)",
  borderRadius: 8,
  color: "inherit",
  padding: "8px 10px",
  font: "inherit",
  width: "100%",
};

export default function Campanhas() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [lists, setLists] = useState<ContactList[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  // forms
  const [listName, setListName] = useState("");
  const [selList, setSelList] = useState("");
  const [bulk, setBulk] = useState(""); // "nome, +5538..." per line
  const [cName, setCName] = useState("");
  const [msgs, setMsgs] = useState("Oi {{name}}! Novidade 1\nOlá {{name}}, novidade 2");
  const [interval, setIntervalS] = useState(0);

  async function reload() {
    const [ls, cs] = await Promise.all([api.contactLists(agencyId), api.campaigns(agencyId)]);
    setLists(ls);
    setCampaigns(cs);
    if (!selList && ls.length) setSelList(ls[0].id);
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await reload();
      } catch (err) {
        if (alive) setNotice(err instanceof Error ? err.message : "erro");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    const t = setInterval(() => {
      api.campaigns(agencyId).then(setCampaigns).catch(() => {});
    }, 3000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function createList() {
    if (!listName.trim()) return;
    try {
      await api.createContactList(listName.trim());
      setListName("");
      await reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha");
    }
  }

  async function addContacts() {
    if (!selList || !bulk.trim()) return;
    const items = bulk
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const [name, number] = l.split(/[,;]/).map((s) => s.trim());
        return number ? { name, number } : { name: "", number: name };
      });
    try {
      const r = await api.addContactItems(selList, items);
      setNotice(`${r.added} contato(s) adicionados`);
      setBulk("");
      await reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha");
    }
  }

  async function launch(scheduleNow: boolean) {
    if (!cName.trim() || !selList) return;
    const messages = msgs.split("\n").map((m) => m.trim()).filter(Boolean);
    if (!messages.length) return;
    try {
      await api.createCampaign({
        name: cName.trim(),
        contact_list_id: selList,
        messages,
        interval_seconds: interval,
        schedule_now: scheduleNow,
      });
      setCName("");
      await reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha");
    }
  }

  if (loading) return <div className="muted">Carregando…</div>;

  return (
    <div>
      <div className="crumb">Campanhas · disparo em massa (dry-run)</div>
      <h1 className="h1">Campanhas</h1>
      {notice && <div className="notice">{notice}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
        {/* coluna esquerda: listas */}
        <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
          <b>Listas de contatos</b>
          <div style={{ display: "flex", gap: 8 }}>
            <input style={inp} placeholder="Nova lista…" value={listName} onChange={(e) => setListName(e.target.value)} />
            <button className="btn-ghost" onClick={createList}>+ Lista</button>
          </div>
          <select style={inp} value={selList} onChange={(e) => setSelList(e.target.value)}>
            <option value="">Selecione a lista…</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.items})
              </option>
            ))}
          </select>
          <textarea
            style={{ ...inp, minHeight: 90, fontFamily: "monospace" }}
            placeholder={"Cliente A, +5538999990001\nCliente B, +5538999990002"}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
          />
          <button className="btn-ghost" onClick={addContacts} disabled={!selList}>
            + Adicionar contatos
          </button>
        </div>

        {/* coluna direita: criar campanha */}
        <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
          <b>Nova campanha</b>
          <input style={inp} placeholder="Nome da campanha" value={cName} onChange={(e) => setCName(e.target.value)} />
          <label className="mono muted" style={{ fontSize: 11 }}>
            Variações de mensagem (1 por linha — rotação anti-ban; use {"{{name}}"})
          </label>
          <textarea
            style={{ ...inp, minHeight: 90 }}
            value={msgs}
            onChange={(e) => setMsgs(e.target.value)}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="mono muted" style={{ fontSize: 11 }}>intervalo (s)</span>
            <input
              style={{ ...inp, width: 80 }}
              type="number"
              min={0}
              value={interval}
              onChange={(e) => setIntervalS(Number(e.target.value))}
            />
            <button className="btn-ghost" onClick={() => launch(false)}>Salvar rascunho</button>
            <button className="btn-ghost" onClick={() => launch(true)} disabled={!selList}>
              ▶ Disparar agora
            </button>
          </div>
        </div>
      </div>

      <h2 className="h1" style={{ fontSize: 18, marginTop: 24 }}>Campanhas</h2>
      <div className="inbox" style={{ display: "grid", gap: 8 }}>
        {campaigns.length === 0 && <div className="empty">Nenhuma campanha.</div>}
        {campaigns.map((c) => {
          const pct = c.total ? Math.round((c.sent / c.total) * 100) : 0;
          return (
            <div key={c.id} className="sess" style={{ cursor: "default" }}>
              <div className="top">
                <span className="nm ellipsis">{c.name}</span>
                <span className={"pill " + (statusPill[c.status] ?? "")}>{c.status}</span>
              </div>
              <div className="mono muted" style={{ fontSize: 11, marginTop: 4 }}>
                {c.list_name ?? "—"} · {c.sent}/{c.total} enviados ({pct}%)
              </div>
              <div style={{ height: 6, background: "rgba(255,255,255,.08)", borderRadius: 4, marginTop: 6 }}>
                <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent, #00f0ff)", borderRadius: 4 }} />
              </div>
              {(c.status === "draft" || c.status === "running" || c.status === "scheduled") && (
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  {c.status === "draft" && (
                    <button className="btn-ghost" onClick={() => api.campaignAction(c.id, "schedule").then(reload)}>
                      ▶ Disparar
                    </button>
                  )}
                  <button className="btn-ghost" onClick={() => api.campaignAction(c.id, "cancel").then(reload)}>
                    Cancelar
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
