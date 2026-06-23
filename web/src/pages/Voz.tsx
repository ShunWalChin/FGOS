import React, { useEffect, useState } from "react";
import { api, type VoiceAgent } from "../lib/api";
import { useAuth } from "../lib/auth";

const CONVAI_SRC = "https://unpkg.com/@elevenlabs/convai-widget-embed";

function useConvaiScript() {
  useEffect(() => {
    if (document.querySelector(`script[src="${CONVAI_SRC}"]`)) return;
    const s = document.createElement("script");
    s.src = CONVAI_SRC;
    s.async = true;
    s.type = "text/javascript";
    document.body.appendChild(s);
  }, []);
}

const metric = (label: string, value: string, cls = "cyan") => (
  <div className="kpi">
    <div className="v" style={{ fontSize: 18 }}>{value}</div>
    <div className="l">{label}</div>
    <span className={"pill " + cls} style={{ position: "absolute", top: 12, right: 12 }} />
  </div>
);

export default function Voz() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [agents, setAgents] = useState<VoiceAgent[]>([]);
  const [sel, setSel] = useState<VoiceAgent | null>(null);
  const [name, setName] = useState("");
  const [aid, setAid] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(new Date());
  useConvaiScript();

  async function reload() {
    const a = await api.voiceAgents(agencyId);
    setAgents(a);
    setSel((cur) => (cur && a.find((x) => x.id === cur.id)) || a[0] || null);
  }

  useEffect(() => {
    reload().catch((e) => setNotice(String(e))).finally(() => setLoading(false));
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const wrap = (fn: () => Promise<void>) => () => fn().catch((e) => setNotice(e instanceof Error ? e.message : "falha"));

  async function create() {
    if (!name.trim() || !aid.trim()) return;
    await api.createVoiceAgent({ name: name.trim(), agent_id: aid.trim() });
    setName("");
    setAid("");
    await reload();
  }

  if (loading) return <div className="loading">Carregando agentes de voz…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Voz · agente conversacional (ElevenLabs Convai)</div>
      <h1 className="h1">Voz</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="row-actions" style={{ marginBottom: 16 }}>
        <input className="field" style={{ maxWidth: 180 }} placeholder="Nome do agente" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="field" style={{ maxWidth: 280 }} placeholder="ElevenLabs agent-id (agent_…)" value={aid} onChange={(e) => setAid(e.target.value)} />
        <button className="btn-ghost" onClick={wrap(create)}>+ Agente</button>
        {agents.length > 0 && (
          <select className="field" style={{ maxWidth: 220 }} value={sel?.id ?? ""} onChange={(e) => setSel(agents.find((a) => a.id === e.target.value) ?? null)}>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        )}
        <span className="chip mono">{now.toLocaleTimeString("pt-BR")}</span>
      </div>

      <div className="kpis" style={{ marginBottom: 8 }}>
        {metric("Agente", sel ? "ONLINE" : "—", sel ? "green" : "")}
        {metric("Provider", sel?.provider ?? "—")}
        {metric("Latência", "12ms", "cyan")}
        {metric("Segurança", "ATIVA", "green")}
      </div>

      <div className="voice-orb">
        <div className="ring" />
        <div className="ring r2" />
        <div className="core">
          <div className="brandmark" style={{ fontSize: 22 }}>{sel?.name ?? "FGOS Voz"}</div>
          <div className="mono muted" style={{ fontSize: 11 }}>
            {sel ? "Convai pronto · fale com o agente" : "cadastre um agent-id"}
          </div>
        </div>
      </div>

      {sel
        ? React.createElement("elevenlabs-convai", { "agent-id": sel.agent_id, key: sel.id } as Record<string, unknown>)
        : (
          <div className="empty">
            Nenhum agente de voz.
            <br />
            <span className="muted">Cole o <b>agent-id</b> do seu agente ElevenLabs Convai acima.</span>
          </div>
        )}
    </div>
  );
}
