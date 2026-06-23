import { useEffect, useState } from "react";
import { api, type MemoryDoc, type MemoryHit } from "../lib/api";
import { useAuth } from "../lib/auth";

const signalPill: Record<string, string> = { dense: "cyan", sparse: "amber" };

export default function Memoria() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [docs, setDocs] = useState<MemoryDoc[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const [kind, setKind] = useState("note");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<MemoryHit[] | null>(null);
  const [meta, setMeta] = useState<{ dense: number; sparse: number } | null>(null);

  async function reload() {
    setDocs(await api.memoryDocs(agencyId));
  }

  useEffect(() => {
    reload().catch((e) => setNotice(String(e))).finally(() => setLoading(false));
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const wrap = (fn: () => Promise<void>) => () => fn().catch((e) => setNotice(e instanceof Error ? e.message : "falha"));

  async function ingest() {
    if (!title.trim() || !content.trim()) return;
    const r = await api.memoryIngest({ kind, title: title.trim(), content });
    setNotice(`Indexado em ${r.chunks} chunk(s) — embedding + full-text.`);
    setTitle("");
    setContent("");
    await reload();
  }

  async function search() {
    if (!query.trim()) return;
    const r = await api.memorySearch(query.trim(), 6);
    setHits(r.hits);
    setMeta({ dense: r.dense, sparse: r.sparse });
  }

  if (loading) return <div className="loading">Carregando memória…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Memória · RAG híbrido (pgvector + full-text + RRF)</div>
      <h1 className="h1">Memória Semântica</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="split">
        {/* ingestão */}
        <div className="panel formstack">
          <div className="ptitle">Ingerir conhecimento</div>
          <div className="row-actions">
            <select className="field" style={{ maxWidth: 130 }} value={kind} onChange={(e) => setKind(e.target.value)}>
              {["note", "brand", "content", "faq", "url"].map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
            <input className="field" placeholder="Título" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <textarea className="field" style={{ minHeight: 140 }} placeholder="Cole o texto / documento a memorizar…" value={content} onChange={(e) => setContent(e.target.value)} />
          <button className="btn-primary" onClick={wrap(ingest)} disabled={!title.trim() || !content.trim()}>+ Memorizar</button>
          <div className="field-label" style={{ marginTop: 8 }}>Documentos ({docs.length})</div>
          {docs.length === 0 && <div className="empty">Memória vazia.</div>}
          {docs.map((d) => (
            <div key={d.id} className="top">
              <span className="nm ellipsis"><span className="pill" style={{ marginRight: 6 }}>{d.kind}</span>{d.title}</span>
              <span className="mono muted" style={{ fontSize: 10 }}>
                {d.chunks} chunk{d.chunks !== 1 ? "s" : ""}
                <button className="btn-ghost" style={{ padding: "0 6px", marginLeft: 8 }} onClick={() => api.deleteMemoryDoc(d.id).then(reload)}>×</button>
              </span>
            </div>
          ))}
        </div>

        {/* busca híbrida */}
        <div className="panel formstack">
          <div className="ptitle">Busca híbrida</div>
          <div className="row-actions">
            <input className="field" placeholder="pergunte algo…" value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && wrap(search)()} />
            <button className="btn-ghost" onClick={wrap(search)} disabled={!query.trim()}>⌕ Buscar</button>
          </div>
          {meta && (
            <div className="mono muted" style={{ fontSize: 11 }}>
              fusão RRF · <span style={{ color: "var(--primary)" }}>dense {meta.dense}</span> + <span style={{ color: "var(--amber)" }}>sparse {meta.sparse}</span>
            </div>
          )}
          {hits === null && <div className="empty">Faça uma busca para ver o RAG em ação.</div>}
          {hits !== null && hits.length === 0 && <div className="empty">Sem resultados.</div>}
          {(hits ?? []).map((h) => (
            <div key={h.chunk_id} className="sess static">
              <div className="top">
                <span className="nm ellipsis"><span className="pill cyan" style={{ marginRight: 6 }}>#{h.rank}</span>{h.title}</span>
                <span>
                  {h.signals.map((s) => <span key={s} className={"pill " + (signalPill[s] ?? "")} style={{ marginLeft: 4 }}>{s}</span>)}
                </span>
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 6, whiteSpace: "pre-wrap" }}>{h.snippet}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
          Reescrita original do núcleo do <b>RuVector</b>: cada documento é dividido em chunks, com
          <b> embedding denso</b> (pgvector, HNSW) e <b>índice esparso</b> (full-text). A busca combina
          os dois rankings via <b>Reciprocal Rank Fusion (RRF)</b> — o que o RuVector chama de retrieval
          híbrido. Conecte um modelo de embeddings real no painel <b>IA</b> para subir a qualidade.
        </div>
      </div>
    </div>
  );
}
