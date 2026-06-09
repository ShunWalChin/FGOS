import { useEffect, useState } from "react";
import { api, ApiError, type Breakdown, type Summary } from "../lib/api";
import { useAuth } from "../lib/auth";

const brl = (cents: number) =>
  (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function Dashboard() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [summary, setSummary] = useState<Summary | null>(null);
  const [breakdown, setBreakdown] = useState<Breakdown[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [s, b] = await Promise.all([api.summary(agencyId), api.breakdown(agencyId)]);
        if (!alive) return;
        setSummary(s);
        setBreakdown(b);
      } catch (err) {
        if (!alive) return;
        const msg =
          err instanceof ApiError && err.status >= 500
            ? "ClickHouse indisponível — suba o stack (worker-bi + clickhouse) para ver os dados."
            : err instanceof Error
              ? err.message
              : "erro";
        setError(msg);
      }
    })();
    return () => {
      alive = false;
    };
  }, [agencyId]);

  const max = Math.max(1, ...breakdown.map((b) => b.n));
  const kpis: Array<[string, string | number, string]> = summary
    ? [
        ["Eventos", summary.total_events.toLocaleString("pt-BR"), "var(--primary)"],
        ["Tipos", summary.event_types, "var(--accent)"],
        ["Valor em deals", brl(summary.deal_value_cents), "var(--green)"],
        ["Posts publicados", summary.posts_published, "var(--secondary)"],
        ["Msgs recebidas", summary.msgs_in, "var(--primary)"],
        ["Msgs enviadas", summary.msgs_out, "var(--accent)"],
      ]
    : [];

  return (
    <div>
      <h1 className="h1">Dashboard</h1>
      {error && <div className="notice">⚠ {error}</div>}

      <section className="kpis">
        {kpis.map(([label, value, color]) => (
          <div className="kpi" key={label}>
            <div className="v" style={{ color }}>
              {value}
            </div>
            <div className="l">{label}</div>
          </div>
        ))}
        {!summary && !error && <div className="muted">Carregando…</div>}
      </section>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>Tipos de evento</h2>
        {breakdown.length === 0 && <div className="muted">Sem eventos ainda.</div>}
        {breakdown.map((b) => (
          <div className="bar-row" key={b.event_type}>
            <span className="mono" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {b.event_type}
            </span>
            <span className="bar" style={{ width: `${(b.n / max) * 100}%` }} />
            <span className="mono" style={{ textAlign: "right" }}>
              {b.n}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
