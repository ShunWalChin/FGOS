import { useEffect, useState } from "react";
import { api, type BrandVoice, type ContentPiece } from "../lib/api";
import { useAuth } from "../lib/auth";

type Tab = "brand" | "content";
const statusPill: Record<string, string> = { draft: "amber", approved: "cyan", published: "green" };

export default function Growth() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [tab, setTab] = useState<Tab>("brand");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [voices, setVoices] = useState<BrandVoice[]>([]);
  const [pieces, setPieces] = useState<ContentPiece[]>([]);

  // brand voice form
  const [bvName, setBvName] = useState("");
  const [bvTone, setBvTone] = useState("profissional, próximo, direto");
  const [bvAvoid, setBvAvoid] = useState("disruptivo, revolucionário");
  const [bvIndustry, setBvIndustry] = useState("");

  // content form
  const [cType, setCType] = useState("copy");
  const [cTitle, setCTitle] = useState("");
  const [cBody, setCBody] = useState("");
  const [cVoice, setCVoice] = useState("");
  const [lint, setLint] = useState<{ ok: boolean; violations: string[] } | null>(null);

  async function reload() {
    const [vs, ps] = await Promise.all([api.brandVoices(agencyId), api.contentPieces()]);
    setVoices(vs);
    setPieces(ps);
    setCVoice((cur) => cur || (vs[0]?.id ?? ""));
  }

  useEffect(() => {
    reload().catch((e) => setNotice(String(e))).finally(() => setLoading(false));
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const wrap = (fn: () => Promise<void>) => () => fn().catch((e) => setNotice(e instanceof Error ? e.message : "falha"));
  const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

  async function createVoice() {
    if (!bvName.trim()) return;
    await api.createBrandVoice({ name: bvName.trim(), tone: csv(bvTone), avoid: csv(bvAvoid), industry: bvIndustry || undefined });
    setBvName("");
    await reload();
  }

  async function createContent() {
    if (!cTitle.trim()) return;
    await api.createContent({ type: cType, title: cTitle.trim(), body: cBody || undefined, brand_voice_id: cVoice || undefined });
    setCTitle("");
    setCBody("");
    setLint(null);
    await reload();
  }

  async function runLint() {
    const r = await api.lintContent(cBody, cVoice || undefined);
    setLint(r);
  }

  if (loading) return <div className="loading">Carregando growth…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Growth · brand voice + produção de conteúdo</div>
      <h1 className="h1">Growth</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="tabs">
        <button className={"tab" + (tab === "brand" ? " on" : "")} onClick={() => setTab("brand")}>Brand Voice</button>
        <button className={"tab" + (tab === "content" ? " on" : "")} onClick={() => setTab("content")}>Conteúdo</button>
      </div>

      {tab === "brand" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Nova brand voice</div>
            <input className="field" placeholder="Nome (ex.: FAT Tech)" value={bvName} onChange={(e) => setBvName(e.target.value)} />
            <span className="field-label">tom (separado por vírgula)</span>
            <input className="field" value={bvTone} onChange={(e) => setBvTone(e.target.value)} />
            <span className="field-label">evitar (palavras/clichês)</span>
            <input className="field" value={bvAvoid} onChange={(e) => setBvAvoid(e.target.value)} />
            <input className="field" placeholder="Indústria (opcional)" value={bvIndustry} onChange={(e) => setBvIndustry(e.target.value)} />
            <button className="btn-ghost" onClick={wrap(createVoice)}>+ Brand voice</button>
          </div>
          <div className="panel formstack">
            <div className="ptitle">Brand voices</div>
            {voices.length === 0 && <div className="empty">Nenhuma brand voice.</div>}
            {voices.map((v) => (
              <div key={v.id}>
                <div className="top">
                  <span className="nm ellipsis">{v.name}</span>
                  <span className="pill">{v.autonomy}</span>
                </div>
                <div className="muted mono" style={{ fontSize: 11 }}>
                  tom: {v.tone.join(" · ") || "—"}{v.industry ? ` · ${v.industry}` : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "content" && (
        <>
          <div className="split">
            <div className="panel formstack">
              <div className="ptitle">Novo conteúdo</div>
              <div className="row-actions">
                <select className="field" style={{ maxWidth: 150 }} value={cType} onChange={(e) => setCType(e.target.value)}>
                  {["copy", "carousel", "video_brief", "sales_page", "seo"].map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
                <select className="field" value={cVoice} onChange={(e) => setCVoice(e.target.value)}>
                  <option value="">brand voice…</option>
                  {voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </div>
              <input className="field" placeholder="Título" value={cTitle} onChange={(e) => setCTitle(e.target.value)} />
              <textarea className="field" style={{ minHeight: 110 }} placeholder="Corpo do conteúdo…" value={cBody} onChange={(e) => { setCBody(e.target.value); setLint(null); }} />
              <div className="row-actions">
                <button className="btn-ghost" onClick={wrap(runLint)} disabled={!cBody.trim()}>⚑ Lint anti-slop</button>
                <button className="btn-primary" onClick={wrap(createContent)}>+ Conteúdo</button>
              </div>
              {lint && (
                <div className="notice" style={{ borderLeftColor: lint.ok ? "var(--green)" : "var(--secondary)" }}>
                  {lint.ok ? "✓ Sem clichês/anti-slop." : `⚠ ${lint.violations.length} flag(s): ${lint.violations.join(", ")}`}
                </div>
              )}
            </div>
            <div className="panel formstack">
              <div className="ptitle">Conteúdos</div>
              {pieces.length === 0 && <div className="empty">Nenhum conteúdo.</div>}
              {pieces.map((p) => (
                <div key={p.id} className="sess static">
                  <div className="top">
                    <span className="nm ellipsis">{p.title}</span>
                    <span className={"pill " + (statusPill[p.status] ?? "")}>{p.status}</span>
                  </div>
                  <div className="muted mono" style={{ fontSize: 11 }}>{p.type}{p.platform ? ` · ${p.platform}` : ""}</div>
                  <div className="row-actions" style={{ marginTop: 8 }}>
                    {p.status === "draft" && <button className="btn-ghost" onClick={() => api.updateContent(p.id, { status: "approved" }).then(reload)}>Aprovar</button>}
                    {p.status === "approved" && <button className="btn-ghost" onClick={() => api.updateContent(p.id, { status: "published" }).then(reload)}>Publicar</button>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
