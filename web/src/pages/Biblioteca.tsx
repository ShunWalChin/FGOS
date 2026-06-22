import { useEffect, useState } from "react";
import { api, type Caption, type MediaItem } from "../lib/api";
import { useAuth } from "../lib/auth";

const inp: React.CSSProperties = {
  background: "rgba(255,255,255,.04)",
  border: "1px solid rgba(255,255,255,.12)",
  borderRadius: 8,
  color: "inherit",
  padding: "8px 10px",
  font: "inherit",
  width: "100%",
};
type Tab = "captions" | "midia";
type Crumb = { id: string | null; name: string };

export default function Biblioteca() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [tab, setTab] = useState<Tab>("captions");
  const [notice, setNotice] = useState("");

  // captions
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [capTitle, setCapTitle] = useState("");
  const [capBody, setCapBody] = useState("");

  // media
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
    <div>
      <div className="crumb">Biblioteca · conteúdo do Módulo B</div>
      <h1 className="h1">Biblioteca</h1>
      {notice && <div className="notice">{notice}</div>}

      <div style={{ display: "flex", gap: 8, margin: "8px 0 16px" }}>
        {(["captions", "midia"] as Tab[]).map((k) => (
          <button
            key={k}
            className={"pill " + (tab === k ? "cyan" : "")}
            style={{ cursor: "pointer" }}
            onClick={() => setTab(k)}
          >
            {k === "captions" ? "Legendas" : "Mídia"}
          </button>
        ))}
      </div>

      {tab === "captions" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Nova legenda</b>
            <input style={inp} placeholder="Título" value={capTitle} onChange={(e) => setCapTitle(e.target.value)} />
            <textarea
              style={{ ...inp, minHeight: 100 }}
              placeholder="Conteúdo da legenda… use {{oferta}}"
              value={capBody}
              onChange={(e) => setCapBody(e.target.value)}
            />
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
          <div className="sess" style={{ cursor: "default", display: "grid", gap: 8 }}>
            <b>Legendas salvas</b>
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
        <div style={{ display: "grid", gap: 12 }}>
          {/* breadcrumb */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            {path.map((c, idx) => (
              <span key={idx}>
                <button
                  className="btn-ghost"
                  style={{ padding: "2px 8px" }}
                  onClick={() => setPath((p) => p.slice(0, idx + 1))}
                >
                  {c.name}
                </button>
                {idx < path.length - 1 && <span className="muted"> / </span>}
              </span>
            ))}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input style={{ ...inp, width: 180 }} placeholder="Nova pasta…" value={folderName} onChange={(e) => setFolderName(e.target.value)} />
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
            <input style={{ ...inp, width: 160 }} placeholder="arquivo.png" value={fileName} onChange={(e) => setFileName(e.target.value)} />
            <input style={{ ...inp, width: 200 }} placeholder="url do arquivo" value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} />
            <button
              className="btn-ghost"
              onClick={() =>
                wrap(async () => {
                  if (!fileName.trim()) return;
                  await api.createMedia({
                    name: fileName.trim(),
                    is_folder: false,
                    parent_id: current ?? undefined,
                    url: fileUrl || undefined,
                  });
                  setFileName("");
                  setFileUrl("");
                  setMedia(await api.media(current ?? undefined));
                })
              }
            >
              + Arquivo
            </button>
          </div>

          <div className="inbox" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
            {media.length === 0 && <div className="empty">Pasta vazia.</div>}
            {media.map((m) => (
              <button
                key={m.id}
                className="sess"
                style={{ cursor: m.is_folder ? "pointer" : "default", textAlign: "left" }}
                onClick={() => m.is_folder && setPath((p) => [...p, { id: m.id, name: m.name }])}
              >
                <div className="nm ellipsis">
                  {m.is_folder ? "📁 " : "🖼 "}
                  {m.name}
                </div>
                {!m.is_folder && m.url && (
                  <div className="muted mono" style={{ fontSize: 10 }}>{m.url}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
