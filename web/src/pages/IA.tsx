import { useEffect, useState } from "react";
import { api, type AIModel } from "../lib/api";
import { useAuth } from "../lib/auth";

const statusPill: Record<string, string> = { active: "green", error: "pink", unverified: "amber" };

export default function IA() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [models, setModels] = useState<AIModel[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const [suggested, setSuggested] = useState<Record<string, string[]>>({});
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [provider, setProvider] = useState("openai");
  const [label, setLabel] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  async function reload() {
    setModels(await api.aiModels(agencyId));
  }

  useEffect(() => {
    Promise.all([api.aiModels(agencyId), api.aiProviders()])
      .then(([m, p]) => {
        setModels(m);
        setProviders(p.providers);
        setSuggested(p.suggested);
        setModel(p.suggested[provider]?.[0] ?? "");
      })
      .catch((e) => setNotice(String(e)))
      .finally(() => setLoading(false));
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const wrap = (fn: () => Promise<void>) => () => fn().catch((e) => setNotice(e instanceof Error ? e.message : "falha"));

  function pickProvider(p: string) {
    setProvider(p);
    setModel(suggested[p]?.[0] ?? "");
    if (!label) setLabel(p);
  }

  async function connect() {
    if (!label.trim() || !model.trim() || !apiKey.trim()) return;
    await api.createAiModel({ provider, label: label.trim(), model: model.trim(), api_key: apiKey.trim(), base_url: baseUrl || undefined });
    setApiKey("");
    setLabel("");
    setNotice("Modelo conectado. Clique em Testar para validar a key.");
    await reload();
  }

  async function test(m: AIModel) {
    setNotice(`Testando ${m.label}…`);
    const r = await api.testAiModel(m.id);
    setNotice(r.ok ? `✓ ${m.label} respondeu: ${r.detail}` : `⚠ ${m.label}: ${r.detail}`);
    await reload();
  }

  if (loading) return <div className="loading">Carregando modelos de IA…</div>;

  return (
    <div className="reveal">
      <div className="crumb">IA · modelos & chaves de API (LLMs)</div>
      <h1 className="h1">IA — Modelos</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="split">
        {/* conectar */}
        <div className="panel formstack">
          <div className="ptitle">Conectar LLM</div>
          <span className="field-label">provider</span>
          <select className="field" value={provider} onChange={(e) => pickProvider(e.target.value)}>
            {providers.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <span className="field-label">modelo</span>
          <input className="field" list="model-suggestions" placeholder="modelo" value={model} onChange={(e) => setModel(e.target.value)} />
          <datalist id="model-suggestions">
            {(suggested[provider] ?? []).map((m) => <option key={m} value={m} />)}
          </datalist>
          <input className="field" placeholder="Apelido (ex.: GPT-4o produção)" value={label} onChange={(e) => setLabel(e.target.value)} />
          <span className="field-label">API key (guardada criptografada)</span>
          <input className="field" type="password" placeholder="sk-…" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          {(provider === "openrouter" || provider === "together" || provider === "xai") && (
            <input className="field" placeholder="base_url (opcional)" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
          )}
          <button className="btn-primary" onClick={wrap(connect)} disabled={!label.trim() || !model.trim() || !apiKey.trim()}>+ Conectar modelo</button>
          <span className="field-label">Providers: {providers.join(" · ")}</span>
        </div>

        {/* lista */}
        <div className="panel formstack">
          <div className="ptitle">Modelos conectados</div>
          {models.length === 0 && <div className="empty">Nenhum modelo. Conecte um LLM para ativar a geração de conteúdo com IA.</div>}
          {models.map((m) => (
            <div key={m.id} className="sess static">
              <div className="top">
                <span className="nm ellipsis">
                  {m.is_default && <span className="pill cyan" style={{ marginRight: 6 }}>padrão</span>}
                  {m.label}
                </span>
                <span className={"pill " + (statusPill[m.status] ?? "")}>{m.status}</span>
              </div>
              <div className="mono muted" style={{ fontSize: 11, marginTop: 3 }}>
                {m.provider} · {m.model}{m.has_key ? " · 🔑" : ""}
              </div>
              {m.last_error && <div className="mono" style={{ fontSize: 10, color: "var(--secondary)", marginTop: 4 }}>{m.last_error.slice(0, 120)}</div>}
              <div className="row-actions" style={{ marginTop: 8 }}>
                {!m.is_default && <button className="btn-ghost" onClick={() => api.setDefaultAiModel(m.id).then(reload)}>Tornar padrão</button>}
                <button className="btn-ghost" onClick={wrap(() => test(m))}>Testar</button>
                <button className="btn-ghost" onClick={() => api.deleteAiModel(m.id).then(reload)}>Remover</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <h2 className="h2">Como funciona</h2>
      <div className="panel">
        <div className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
          O modelo marcado como <b>padrão</b> é usado pelo <b>worker de geração de conteúdo</b> (tela Growth → "✨ Gerar com IA").
          Sem modelo, a geração roda em <b>dry-run</b> (rascunho determinístico). As chaves ficam
          <b> criptografadas no banco</b> (pgcrypto) e nunca são devolvidas pela API.
        </div>
      </div>
    </div>
  );
}
