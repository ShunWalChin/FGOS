import { useEffect, useState } from "react";
import { api, type Ticket, type Queue, type Contact } from "../lib/api";
import { useAuth } from "../lib/auth";

const statusPill: Record<string, string> = { pending: "amber", open: "green", closed: "cyan" };
const TABS: Array<["pending" | "open" | "closed", string]> = [
  ["pending", "Pendentes"],
  ["open", "Em atendimento"],
  ["closed", "Fechados"],
];

export default function Atendimento() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [tab, setTab] = useState<"pending" | "open" | "closed">("pending");
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [newQueue, setNewQueue] = useState("");
  const [newContact, setNewContact] = useState("");

  async function refresh(which: "pending" | "open" | "closed") {
    try {
      setTickets(await api.tickets(which));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "erro");
    }
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [t, qs, cs] = await Promise.all([
          api.tickets(tab),
          api.queues(agencyId),
          api.contacts(agencyId),
        ]);
        if (!alive) return;
        setTickets(t);
        setQueues(qs);
        setContacts(cs);
      } catch (err) {
        if (alive) setNotice(err instanceof Error ? err.message : "erro");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [agencyId, tab]);

  const wrap = (fn: () => Promise<void>) => () =>
    fn().catch((err) => setNotice(err instanceof Error ? err.message : "falha"));

  async function createQueue() {
    if (!newQueue.trim()) return;
    await api.createQueue({ name: newQueue.trim(), greeting_message: "Olá! Como posso ajudar?" });
    setNewQueue("");
    setQueues(await api.queues(agencyId));
  }

  async function createTicket() {
    if (!newContact) return;
    await api.createTicket({ contact_id: newContact, queue_id: queues[0]?.id, channel: "whatsapp", last_message: "Novo atendimento" });
    setNewContact("");
    setTab("pending");
    await refresh("pending");
  }

  async function assign(t: Ticket) {
    await api.updateTicket(t.id, { assigned_user_id: user!.id, status: "open" });
    setTab("open");
    await refresh("open");
  }

  async function closeTicket(t: Ticket) {
    await api.updateTicket(t.id, { status: "closed" });
    await refresh(tab);
  }

  if (loading) return <div className="loading">Carregando atendimentos…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Atendimento · inbox multi-atendente</div>
      <h1 className="h1">Atendimento</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="tabs">
        {TABS.map(([key, label]) => (
          <button key={key} className={"tab" + (tab === key ? " on" : "")} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      <div className="row-actions" style={{ marginBottom: 16 }}>
        <input className="field" style={{ maxWidth: 200 }} placeholder="Nova fila…" value={newQueue} onChange={(e) => setNewQueue(e.target.value)} />
        <button className="btn-ghost" onClick={wrap(createQueue)}>+ Fila</button>
        <select className="field" style={{ maxWidth: 240 }} value={newContact} onChange={(e) => setNewContact(e.target.value)}>
          <option value="">Abrir ticket para…</option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>{c.full_name ?? c.phone ?? c.email ?? c.id}</option>
          ))}
        </select>
        <button className="btn-ghost" onClick={wrap(createTicket)} disabled={!newContact}>+ Ticket</button>
        <span className="chip mono">{queues.length} fila(s)</span>
      </div>

      <div className="inbox" style={{ display: "grid", gap: 8 }}>
        {tickets.length === 0 && <div className="empty">Nenhum ticket aqui.</div>}
        {tickets.map((t) => (
          <div key={t.id} className="sess static">
            <div className="top">
              <span className="nm ellipsis">{t.contact_label}</span>
              <span className={"pill " + (statusPill[t.status] ?? "")}>{t.status}</span>
            </div>
            <div className="pv ellipsis">{t.last_message ?? "—"}</div>
            <div className="mono muted" style={{ fontSize: 11, marginTop: 4 }}>
              {t.queue_name ? `fila: ${t.queue_name}` : "sem fila"}
              {t.agent_name ? ` · ${t.agent_name}` : ""}
            </div>
            <div className="row-actions" style={{ marginTop: 8 }}>
              {t.status === "pending" && <button className="btn-ghost" onClick={wrap(() => assign(t))}>Assumir</button>}
              {t.status !== "closed" && <button className="btn-ghost" onClick={wrap(() => closeTicket(t))}>Fechar</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
