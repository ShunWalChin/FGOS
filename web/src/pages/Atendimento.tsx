import { useEffect, useState } from "react";
import { api, type Ticket, type Queue, type Contact } from "../lib/api";
import { useAuth } from "../lib/auth";

const statusPill: Record<string, string> = { pending: "amber", open: "green", closed: "cyan" };
const TABS: Array<["pending" | "open" | "closed", string]> = [
  ["pending", "Pendentes"],
  ["open", "Em atendimento"],
  ["closed", "Fechados"],
];
const inp: React.CSSProperties = {
  background: "rgba(255,255,255,.04)",
  border: "1px solid rgba(255,255,255,.12)",
  borderRadius: 8,
  color: "inherit",
  padding: "8px 10px",
  font: "inherit",
};

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

  async function createQueue() {
    if (!newQueue.trim()) return;
    try {
      await api.createQueue({ name: newQueue.trim(), greeting_message: "Olá! Como posso ajudar?" });
      setNewQueue("");
      setQueues(await api.queues(agencyId));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao criar fila");
    }
  }

  async function createTicket() {
    if (!newContact) return;
    try {
      await api.createTicket({
        contact_id: newContact,
        queue_id: queues[0]?.id,
        channel: "whatsapp",
        last_message: "Novo atendimento",
      });
      setNewContact("");
      setTab("pending");
      await refresh("pending");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao abrir ticket");
    }
  }

  async function assign(t: Ticket) {
    try {
      await api.updateTicket(t.id, { assigned_user_id: user!.id, status: "open" });
      setTab("open");
      await refresh("open");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao assumir");
    }
  }

  async function closeTicket(t: Ticket) {
    try {
      await api.updateTicket(t.id, { status: "closed" });
      await refresh(tab);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao fechar");
    }
  }

  if (loading) return <div className="muted">Carregando…</div>;

  return (
    <div>
      <div className="crumb">Atendimento · inbox multi-atendente</div>
      <h1 className="h1">Atendimento</h1>
      {notice && <div className="notice">{notice}</div>}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0 16px" }}>
        {TABS.map(([key, label]) => (
          <button
            key={key}
            className={"pill " + (tab === key ? statusPill[key] : "")}
            style={{ cursor: "pointer" }}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <input
          style={inp}
          placeholder="Nova fila…"
          value={newQueue}
          onChange={(e) => setNewQueue(e.target.value)}
        />
        <button className="btn-ghost" onClick={createQueue}>
          + Fila
        </button>
        <select style={inp} value={newContact} onChange={(e) => setNewContact(e.target.value)}>
          <option value="">Abrir ticket para…</option>
          {contacts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.full_name ?? c.phone ?? c.email ?? c.id}
            </option>
          ))}
        </select>
        <button className="btn-ghost" onClick={createTicket} disabled={!newContact}>
          + Ticket
        </button>
        <span className="mono muted" style={{ alignSelf: "center" }}>
          {queues.length} fila(s)
        </span>
      </div>

      <div className="inbox" style={{ display: "grid", gap: 8 }}>
        {tickets.length === 0 && <div className="empty">Nenhum ticket aqui.</div>}
        {tickets.map((t) => (
          <div key={t.id} className="sess" style={{ cursor: "default" }}>
            <div className="top">
              <span className="nm ellipsis">{t.contact_label}</span>
              <span className={"pill " + (statusPill[t.status] ?? "")}>{t.status}</span>
            </div>
            <div className="pv ellipsis">{t.last_message ?? "—"}</div>
            <div className="mono muted" style={{ fontSize: 11, marginTop: 4 }}>
              {t.queue_name ? `fila: ${t.queue_name}` : "sem fila"}
              {t.agent_name ? ` · ${t.agent_name}` : ""}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              {t.status === "pending" && (
                <button className="btn-ghost" onClick={() => assign(t)}>
                  Assumir
                </button>
              )}
              {t.status !== "closed" && (
                <button className="btn-ghost" onClick={() => closeTicket(t)}>
                  Fechar
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
