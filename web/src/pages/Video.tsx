import { useEffect, useState } from "react";
import { api, type VideoProject } from "../lib/api";
import { useAuth } from "../lib/auth";

const statusPill: Record<string, string> = { draft: "amber", editing: "cyan", rendered: "green" };

export default function Video() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [projects, setProjects] = useState<VideoProject[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  async function reload() {
    setProjects(await api.videoProjects(agencyId));
  }

  useEffect(() => {
    reload().catch((e) => setNotice(String(e))).finally(() => setLoading(false));
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const wrap = (fn: () => Promise<void>) => () => fn().catch((e) => setNotice(e instanceof Error ? e.message : "falha"));

  async function create() {
    if (!name.trim()) return;
    await api.createVideoProject({ name: name.trim(), editor_url: url || undefined });
    setName("");
    setUrl("");
    await reload();
  }

  function openEditor(p: VideoProject) {
    api.updateVideoProject(p.id, "editing").then(reload).catch(() => {});
    window.open(p.editor_url, "_blank", "noopener,noreferrer");
  }

  if (loading) return <div className="loading">Carregando projetos de vídeo…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Vídeo · editor OpenCut (companheiro)</div>
      <h1 className="h1">Vídeo</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="panel formstack" style={{ maxWidth: 580 }}>
        <div className="ptitle">Novo projeto</div>
        <input className="field" placeholder="Nome do projeto" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="field" placeholder="URL do editor (padrão: opencut.app)" value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn-primary" onClick={wrap(create)} disabled={!name.trim()}>+ Projeto de vídeo</button>
      </div>

      <h2 className="h2">Projetos</h2>
      <div className="media-grid">
        {projects.length === 0 && <div className="empty">Nenhum projeto de vídeo.</div>}
        {projects.map((p) => (
          <div key={p.id} className="media-tile" style={{ cursor: "default" }}>
            <div className="top">
              <span className="nm ellipsis">🎬 {p.name}</span>
              <span className={"pill " + (statusPill[p.status] ?? "")}>{p.status}</span>
            </div>
            <div className="mono muted ellipsis" style={{ fontSize: 10 }}>{p.editor_url}</div>
            <div className="row-actions" style={{ marginTop: 6 }}>
              <button className="btn-ghost" onClick={() => openEditor(p)}>▶ Abrir editor</button>
              {p.status !== "rendered" && (
                <button className="btn-ghost" onClick={() => api.updateVideoProject(p.id, "rendered").then(reload)}>Renderizado</button>
              )}
              <button className="btn-ghost" onClick={() => api.deleteVideoProject(p.id).then(reload)}>Remover</button>
            </div>
          </div>
        ))}
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>
          O FGOS gerencia os <b>projetos de vídeo</b>; a edição acontece no <b>OpenCut</b> (editor
          open-source, MIT). Para self-host, aponte a <b>URL do editor</b> para a sua instância do
          OpenCut; sem URL, abre o app público (opencut.app).
        </div>
      </div>
    </div>
  );
}
