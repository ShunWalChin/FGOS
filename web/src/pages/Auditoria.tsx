import { useEffect, useState } from "react";
import { api, type AuditEvent, type TraceStep, type TicketAudit } from "../lib/api";

type Tab = "eventos" | "tickets";

const nsColor: Record<string, string> = {
  workspace: "cyan",
  crm: "green",
  messaging: "pink",
  social: "amber",
  growth: "cyan",
  bi: "cyan",
};
const colorOf = (eventType: string) => nsColor[eventType.split(".")[0]] ?? "";
const time = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export default function Auditoria() {
  const [tab, setTab] = useState<Tab>("eventos");
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [trace, setTrace] = useState<TraceStep[] | null>(null);
  const [traceId, setTraceId] = useState("");
  const [tickets, setTickets] = useState<TicketAudit[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadEvents() {
    setEvents(await api.auditEvents(filter || undefined));
  }

  useEffect(() => {
    Promise.all([api.auditEvents(), api.auditTickets()])
      .then(([e, t]) => { setEvents(e); setTickets(t); })
      .catch((err) => setNotice(String(err)))
      .finally(() => setLoading(false));
    const i = setInterval(() => {
      api.auditEvents(filter || undefined).then(setEvents).catch(() => {});
    }, 4000);
    return () => clearInterval(i);
  }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openTrace(tid: string) {
    setTraceId(tid);
    try {
      setTrace(await api.auditTrace(tid));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "erro");
    }
  }

  if (loading) return <div className="loading">Carregando auditoria…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Auditoria · console de observabilidade (event bus + trace)</div>
      <h1 className="h1">Auditoria</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="tabs">
        <button className={"tab" + (tab === "eventos" ? " on" : "")} onClick={() => setTab("eventos")}>Eventos</button>
        <button className={"tab" + (tab === "tickets" ? " on" : "")} onClick={() => setTab("tickets")}>Tickets</button>
      </div>

      {tab === "eventos" && (
        <div className="split" style={{ gridTemplateColumns: "1.1fr 1fr" }}>
          {/* live feed */}
          <div className="panel formstack">
            <div className="ptitle">Feed ao vivo <span className="chip mono" style={{ marginLeft: "auto" }}>{events.length}</span></div>
            <input className="field" placeholder="filtrar por tipo (ex.: crm, messaging.ticket)" value={filter} onChange={(e) => setFilter(e.target.value)} />
            <div className="inbox" style={{ display: "grid", gap: 6, maxHeight: 460, overflowY: "auto" }}>
              {events.length === 0 && <div className="empty">Sem eventos.</div>}
              {events.map((e) => (
                <button
                  key={e.event_id || e.occurred_at + e.event_type}
                  className={"sess" + (e.trace_id === traceId ? " active" : "")}
                  onClick={() => e.trace_id && openTrace(e.trace_id)}
                >
                  <div className="top">
                    <span className={"pill " + colorOf(e.event_type)}>{e.event_type}</span>
                    <span className="mono muted" style={{ fontSize: 10 }}>{time(e.occurred_at)} · hop {e.hops}</span>
                  </div>
                  <div className="mono muted ellipsis" style={{ fontSize: 11, marginTop: 3 }}>
                    {e.entity_id ? `#${e.entity_id.slice(0, 8)}` : "—"} · trace {e.trace_id.slice(0, 8)}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* trace viewer */}
          <div className="panel formstack">
            <div className="ptitle">Trace viewer</div>
            {!trace ? (
              <div className="empty">Clique num evento para ver a cadeia (trace).</div>
            ) : (
              <>
                <div className="mono muted" style={{ fontSize: 11 }}>trace {traceId.slice(0, 13)}… · {trace.length} evento(s)</div>
                <div style={{ display: "grid", gap: 0, marginTop: 8 }}>
                  {trace.map((s, idx) => (
                    <div key={s.event_id || idx} style={{ display: "grid", gridTemplateColumns: "44px 1fr", gap: 10 }}>
                      <div style={{ display: "grid", justifyItems: "center" }}>
                        <span className="pill cyan" style={{ padding: "1px 7px" }}>h{s.hops}</span>
                        {idx < trace.length - 1 && <div style={{ width: 2, flex: 1, minHeight: 26, background: "var(--line-2)", marginTop: 2 }} />}
                      </div>
                      <div style={{ paddingBottom: 14 }}>
                        <span className={"pill " + colorOf(s.event_type)}>{s.event_type}</span>
                        <div className="mono muted" style={{ fontSize: 10, marginTop: 4 }}>{time(s.occurred_at)} · {s.entity_id ? `#${s.entity_id.slice(0, 8)}` : "—"}</div>
                        <div className="muted" style={{ fontSize: 11, marginTop: 4, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{(s.meta || "").slice(0, 160)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {tab === "tickets" && (
        <div className="panel formstack">
          <div className="ptitle">Trilha de atendimento (ticket_traking)</div>
          {tickets.length === 0 && <div className="empty">Sem registros de tickets.</div>}
          {tickets.map((t, idx) => (
            <div key={idx} style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 10, alignItems: "baseline" }}>
              <span className="mono muted" style={{ fontSize: 11 }}>{time(t.at)}</span>
              <div>
                <span className="pill amber">{t.action}</span>{" "}
                <span style={{ fontWeight: 600 }}>{t.contact}</span>
                {t.detail && <span className="mono muted" style={{ fontSize: 11 }}> · {t.detail.slice(0, 40)}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
