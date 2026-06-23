import { useEffect, useState } from "react";
import { api, type Caption, type MediaItem } from "../lib/api";
import { useAuth } from "../lib/auth";

type Tab = "captions" | "midia";
type Crumb = { id: string | null; name: string };

export default function Biblioteca() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [tab, setTab] = useState<Tab>("captions");
  const [notice, setNotice] = useState("");

  const [captions, setCaptions] = useState<Caption[]>([]);
  const [capTitle, setCapTitle] = useState("");
  const [capBody, setCapBody] = useState("");

  const [path, setPath] = useState<Crumb[]>([{ id: null, name: "Raiz" }]);
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [folderName, setFolderName] = useState("");
  const [fileName, setFileName] = useState("");
  const [fileUrl, setFileUrl] = useState("");

  const current = path[path.length - 1].id;

  const wrap = async (fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "falha");
    }
  };

  useEffect(() => {
    api.captions(agencyId).then(setCaptions).catch((e) => setNotice(String(e)));
  }, [agencyId]);

  useEffect(() => {
    api.media(current ?? undefined).then(setMedia).catch(() => {});
  }, [current]);

  return (
    <div className="reveal">
      <div className="crumb">Biblioteca · conteúdo do Módulo B</div>
      <h1 className="h1">Biblioteca</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="tabs">
        <button className={"tab" + (tab === "captions" ? " on" : "")} onClick={() => setTab("captions")}>Legendas</button>
        <button className={"tab" + (tab === "midia" ? " on" : "")} onClick={() => setTab("midia")}>Mídia</button>
      </div>

      {tab === "captions" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Nova legenda</div>
            <input className="field" placeholder="Título" value={capTitle} onChange={(e) => setCapTitle(e.target.value)} />
            <textarea className="field" style={{ minHeight: 110 }} placeholder="Conteúdo da legenda… use {{oferta}}" value={capBody} onChange={(e) => setCapBody(e.target.value)} />
            <button
              className="btn-ghost"
              onClick={() =>
                wrap(async () => {
                  if (!capTitle.trim() || !capBody.trim()) return;
                  await api.createCaption({ title: capTitle.trim(), content: capBody });
                  setCapTitle("");
                  setCapBody("");
                  setCaptions(await api.captions(agencyId));
                })
              }
            >
              + Legenda
            </button>
          </div>
          <div className="panel formstack">
            <div className="ptitle">Legendas salvas</div>
            {captions.length === 0 && <div className="empty">Nenhuma legenda.</div>}
            {captions.map((c) => (
              <div key={c.id}>
                <div className="nm ellipsis">{c.title}</div>
                <div className="muted mono" style={{ fontSize: 11 }}>{c.content}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "midia" && (
        <div className="formstack">
          <div className="breadcrumb">
            {path.map((c, idx) => (
              <span key={idx}>
                <button onClick={() => setPath((p) => p.slice(0, idx + 1))}>{c.name}</button>
                {idx < path.length - 1 && <span className="sep">/</span>}
              </span>
            ))}
          </div>

          <div className="row-actions">
            <input className="field" style={{ width: 180 }} placeholder="Nova pasta…" value={folderName} onChange={(e) => setFolderName(e.target.value)} />
            <button
              className="btn-ghost"
              onClick={() =>
                wrap(async () => {
                  if (!folderName.trim()) return;
                  await api.createMedia({ name: folderName.trim(), is_folder: true, parent_id: current ?? undefined });
                  setFolderName("");
                  setMedia(await api.media(current ?? undefined));
                })
              }
            >
              + Pasta
            </button>
            <input className="field" style={{ width: 150 }} placeholder="arquivo.png" value={fileName} onChange={(e) => setFileName(e.target.value)} />
            <input className="field" style={{ width: 190 }} placeholder="url do arquivo" value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} />
            <button
              className="btn-ghost"
              onClick={() =>
                wrap(async () => {
                  if (!fileName.trim()) return;
                  await api.createMedia({ name: fileName.trim(), is_folder: false, parent_id: current ?? undefined, url: fileUrl || undefined });
                  setFileName("");
                  setFileUrl("");
                  setMedia(await api.media(current ?? undefined));
                })
              }
            >
              + Arquivo
            </button>
          </div>

          <div className="media-grid">
            {media.length === 0 && <div className="empty">Pasta vazia.</div>}
            {media.map((m) => (
              <button
                key={m.id}
                className="media-tile"
                style={{ cursor: m.is_folder ? "pointer" : "default" }}
                onClick={() => m.is_folder && setPath((p) => [...p, { id: m.id, name: m.name }])}
              >
                <div className="ico">{m.is_folder ? "📁" : "🖼"}</div>
                <div className="nm ellipsis">{m.name}</div>
                {!m.is_folder && m.url && <div className="muted mono" style={{ fontSize: 10 }}>{m.url}</div>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
