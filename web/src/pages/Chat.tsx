import { useEffect, useState } from "react";
import { api, type ChatSession, type Message } from "../lib/api";
import { useAuth } from "../lib/auth";

const channelPill: Record<string, string> = {
  whatsapp: "green",
  instagram: "pink",
  messenger: "cyan",
};

const time = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

export default function Chat() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [active, setActive] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await api.sessions(agencyId);
        if (alive) setSessions(s);
      } catch (err) {
        if (alive) setNotice(err instanceof Error ? err.message : "erro");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [agencyId]);

  async function open(s: ChatSession) {
    setActive(s);
    setMessages([]);
    try {
      setMessages(await api.messages(s.id));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "erro");
    }
  }

  async function toggleMode() {
    if (!active) return;
    const next = active.mode === "human" ? "bot" : "human";
    try {
      await api.setMode(active.id, next);
      setActive({ ...active, mode: next });
      setSessions((prev) => prev.map((s) => (s.id === active.id ? { ...s, mode: next } : s)));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao trocar modo");
    }
  }

  if (loading) return <div className="muted">Carregando…</div>;

  return (
    <div>
      <div className="crumb">Mensageria · ManyChat</div>
      <h1 className="h1">Mensageria</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className={"chat" + (active ? " has-active" : "")}>
        <div className="inbox">
          {sessions.length === 0 && (
            <div className="empty">
              Nenhuma conversa.
              <br />
              <span className="muted">Mensagens chegam pelo webhook do Meta.</span>
            </div>
          )}
          {sessions.map((s) => (
            <button key={s.id} className={"sess" + (active?.id === s.id ? " active" : "")} onClick={() => open(s)}>
              <div className="top">
                <span className="nm ellipsis">{s.contact_label}</span>
                <span className={"pill " + (channelPill[s.channel] ?? "")}>{s.channel}</span>
              </div>
              <div className="pv ellipsis">
                {s.last_direction === "out" ? "↩ " : ""}
                {s.last_body ?? "—"}
              </div>
            </button>
          ))}
        </div>

        <div className="thread">
          {!active ? (
            <div className="empty">Selecione uma conversa</div>
          ) : (
            <>
              <div className="head">
                <button className="btn-ghost back" onClick={() => setActive(null)}>
                  ←
                </button>
                <div className="grow" style={{ flex: 1, minWidth: 0 }}>
                  <div className="t ellipsis">{active.contact_label}</div>
                  <div className="mono muted" style={{ fontSize: 11 }}>
                    {active.channel}
                  </div>
                </div>
                <button
                  className={"pill " + (active.mode === "human" ? "amber" : "cyan")}
                  onClick={toggleMode}
                  title="alternar bot/humano"
                  style={{ cursor: "pointer" }}
                >
                  <span className="dot" /> {active.mode === "human" ? "Humano" : "Bot"}
                </button>
              </div>
              <div className="body">
                {messages.length === 0 && <div className="empty">Sem mensagens.</div>}
                {messages.map((m) => (
                  <div key={m.id} className={"bubble " + m.direction}>
                    {m.body}
                    <span className="ts">{time(m.created_at)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
