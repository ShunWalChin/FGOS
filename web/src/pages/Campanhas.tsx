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

export default function Campanhas() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [lists, setLists] = useState<ContactList[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [listName, setListName] = useState("");
  const [selList, setSelList] = useState("");
  const [bulk, setBulk] = useState("");
  const [cName, setCName] = useState("");
  const [msgs, setMsgs] = useState("Oi {{name}}! Novidade 1\nOlá {{name}}, novidade 2");
  const [interval, setIntervalS] = useState(0);

  async function reload() {
    const [ls, cs] = await Promise.all([api.contactLists(agencyId), api.campaigns(agencyId)]);
    setLists(ls);
    setCampaigns(cs);
    setSelList((cur) => cur || (ls[0]?.id ?? ""));
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

  const wrap = async (fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha");
    }
  };

  async function createList() {
    if (!listName.trim()) return;
    await api.createContactList(listName.trim());
    setListName("");
    await reload();
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
    const r = await api.addContactItems(selList, items);
    setNotice(`${r.added} contato(s) adicionados`);
    setBulk("");
    await reload();
  }

  async function launch(scheduleNow: boolean) {
    if (!cName.trim() || !selList) return;
    const messages = msgs.split("\n").map((m) => m.trim()).filter(Boolean);
    if (!messages.length) return;
    await api.createCampaign({
      name: cName.trim(),
      contact_list_id: selList,
      messages,
      interval_seconds: interval,
      schedule_now: scheduleNow,
    });
    setCName("");
    await reload();
  }

  if (loading) return <div className="loading">Carregando campanhas…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Campanhas · disparo em massa (dry-run)</div>
      <h1 className="h1">Campanhas</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="split">
        {/* listas de contatos */}
        <div className="panel formstack">
          <div className="ptitle">Listas de contatos</div>
          <div className="row-actions">
            <input className="field" placeholder="Nova lista…" value={listName} onChange={(e) => setListName(e.target.value)} />
            <button className="btn-ghost" onClick={() => wrap(createList)}>+ Lista</button>
          </div>
          <select className="field" value={selList} onChange={(e) => setSelList(e.target.value)}>
            <option value="">Selecione a lista…</option>
            {lists.map((l) => (
              <option key={l.id} value={l.id}>{l.name} ({l.items})</option>
            ))}
          </select>
          <span className="field-label">um contato por linha — "nome, +5538..."</span>
          <textarea
            className="field"
            style={{ fontFamily: "var(--mono, monospace)" }}
            placeholder={"Cliente A, +5538999990001\nCliente B, +5538999990002"}
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
          />
          <button className="btn-ghost" onClick={() => wrap(addContacts)} disabled={!selList}>+ Adicionar contatos</button>
        </div>

        {/* nova campanha */}
        <div className="panel formstack">
          <div className="ptitle">Nova campanha</div>
          <input className="field" placeholder="Nome da campanha" value={cName} onChange={(e) => setCName(e.target.value)} />
          <span className="field-label">variações de mensagem — 1 por linha (rotação anti-ban; use {"{{name}}"})</span>
          <textarea className="field" value={msgs} onChange={(e) => setMsgs(e.target.value)} />
          <div className="row-actions">
            <span className="field-label">intervalo (s)</span>
            <input className="field" style={{ width: 80 }} type="number" min={0} value={interval} onChange={(e) => setIntervalS(Number(e.target.value))} />
            <button className="btn-ghost" onClick={() => wrap(() => launch(false))}>Salvar rascunho</button>
            <button className="btn-primary" onClick={() => wrap(() => launch(true))} disabled={!selList}>▶ Disparar agora</button>
          </div>
        </div>
      </div>

      <h2 className="h2">Campanhas</h2>
      <div className="inbox" style={{ display: "grid", gap: 8 }}>
        {campaigns.length === 0 && <div className="empty">Nenhuma campanha.</div>}
        {campaigns.map((c) => {
          const pct = c.total ? Math.round((c.sent / c.total) * 100) : 0;
          return (
            <div key={c.id} className="sess static">
              <div className="top">
                <span className="nm ellipsis">{c.name}</span>
                <span className={"pill " + (statusPill[c.status] ?? "")}>{c.status}</span>
              </div>
              <div className="mono muted" style={{ fontSize: 11, marginTop: 4 }}>
                {c.list_name ?? "—"} · {c.sent}/{c.total} enviados ({pct}%)
              </div>
              <div className="progress"><i style={{ width: `${pct}%` }} /></div>
              {(c.status === "draft" || c.status === "running" || c.status === "scheduled") && (
                <div className="row-actions" style={{ marginTop: 8 }}>
                  {c.status === "draft" && (
                    <button className="btn-ghost" onClick={() => api.campaignAction(c.id, "schedule").then(reload)}>▶ Disparar</button>
                  )}
                  <button className="btn-ghost" onClick={() => api.campaignAction(c.id, "cancel").then(reload)}>Cancelar</button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
