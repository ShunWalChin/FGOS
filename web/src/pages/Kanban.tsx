import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Deal, type Stage } from "../lib/api";
import { useAuth } from "../lib/auth";

const brl = (cents: number) =>
  (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function Kanban() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const reloadDeals = useCallback(async () => {
    setDeals(await api.deals(agencyId));
  }, [agencyId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const pipelines = await api.pipelines(agencyId);
        if (!alive) return;
        if (pipelines.length === 0) {
          setNotice("Nenhuma pipeline. Rode `fgos seed` ou crie uma agência no onboarding.");
          setLoading(false);
          return;
        }
        const pid = pipelines[0].id;
        const [st, dl] = await Promise.all([api.stages(pid), api.deals(agencyId)]);
        if (!alive) return;
        setPipelineId(pid);
        setStages(st);
        setDeals(dl);
      } catch (err) {
        if (alive) setNotice(err instanceof Error ? err.message : "erro ao carregar");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [agencyId]);

  async function move(deal: Deal, dir: -1 | 1) {
    const idx = stages.findIndex((s) => s.id === deal.stage_id);
    const target = stages[idx + dir];
    if (!target) return;
    setNotice("");
    // optimistic: move locally, roll back on failure
    setDeals((prev) => prev.map((d) => (d.id === deal.id ? { ...d, stage_id: target.id } : d)));
    try {
      await api.moveDeal(deal.id, target.id, deal.value_cents ? 0 : 0, deal.version);
      await reloadDeals();
    } catch (err) {
      await reloadDeals(); // rollback to server truth
      if (err instanceof ApiError && err.status === 409) {
        setNotice("Conflito de versão (409) — o card foi atualizado por outro lugar. Recarregado.");
      } else {
        setNotice(err instanceof Error ? err.message : "falha ao mover");
      }
    }
  }

  async function addDeal() {
    if (!pipelineId || stages.length === 0) return;
    const title = prompt("Título do novo lead/deal:");
    if (!title) return;
    const valueStr = prompt("Valor estimado (R$):", "0") ?? "0";
    const cents = Math.round(parseFloat(valueStr.replace(",", ".")) * 100) || 0;
    try {
      await api.createDeal({
        agency_id: agencyId,
        pipeline_id: pipelineId,
        stage_id: stages[0].id,
        title,
        value_cents: cents,
      });
      await reloadDeals();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao criar");
    }
  }

  if (loading) return <div className="muted">Carregando…</div>;

  return (
    <div>
      <div className="toolbar">
        <h1 className="h1" style={{ margin: 0 }}>
          CRM Kanban
        </h1>
        <span className="spacer" style={{ flex: 1 }} />
        <button className="btn-primary" style={{ width: "auto", marginTop: 0 }} onClick={addDeal}>
          + Novo deal
        </button>
      </div>
      {notice && <div className="notice">{notice}</div>}

      <div className="board">
        {stages.map((stage, i) => {
          const cards = deals.filter((d) => d.stage_id === stage.id);
          return (
            <div className={"col" + (stage.is_won ? " won" : "")} key={stage.id}>
              <h3>
                <span>{stage.name}</span>
                <span className="count">{cards.length}</span>
              </h3>
              {cards.map((d) => (
                <div className="deal" key={d.id}>
                  <div className="t">{d.title}</div>
                  <div className="v">{brl(d.value_cents)}</div>
                  <div className="row">
                    <span className="mono muted" style={{ fontSize: 11 }}>
                      v{d.version}
                    </span>
                    <span className="move">
                      <button disabled={i === 0} onClick={() => move(d, -1)} title="voltar etapa">
                        ←
                      </button>
                      <button disabled={i === stages.length - 1} onClick={() => move(d, 1)} title="avançar etapa">
                        →
                      </button>
                    </span>
                  </div>
                </div>
              ))}
              {cards.length === 0 && <div className="muted" style={{ fontSize: 13 }}>—</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
