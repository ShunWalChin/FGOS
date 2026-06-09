import { useEffect, useState, type FormEvent } from "react";
import { api, type Post, type SocialAccount } from "../lib/api";
import { useAuth } from "../lib/auth";

const PLATFORMS = ["meta", "tiktok", "linkedin", "youtube"];

const statusPill = (s: string) =>
  s === "published" || s === "active"
    ? "green"
    : s === "failed" || s === "disconnected"
      ? "pink"
      : s === "rate_limited"
        ? "amber"
        : "cyan";

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";

export default function Social() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  // schedule form
  const [accId, setAccId] = useState("");
  const [caption, setCaption] = useState("");
  const [when, setWhen] = useState("");

  async function reload() {
    const [a, p] = await Promise.all([api.socialAccounts(agencyId), api.posts(agencyId)]);
    setAccounts(a);
    setPosts(p);
    if (a.length && !accId) setAccId(a[0].id);
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await reload();
      } catch (err) {
        if (alive) setNotice(err instanceof Error ? err.message : "erro");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agencyId]);

  async function connect() {
    const platform = prompt(`Plataforma (${PLATFORMS.join("/")}):`, "meta");
    if (!platform || !PLATFORMS.includes(platform)) return;
    const ext = prompt("ID externo da conta (ex: page id / @user):");
    if (!ext) return;
    const token = prompt("Access token (dry-run em dev):", "dev-token");
    if (!token) return;
    try {
      await api.connectAccount({ agency_id: agencyId, platform, external_account_id: ext, access_token: token });
      await reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao conectar");
    }
  }

  async function schedule(e: FormEvent) {
    e.preventDefault();
    if (!accId || !when) return;
    try {
      await api.schedulePost({
        agency_id: agencyId,
        social_account_id: accId,
        caption,
        scheduled_at: new Date(when).toISOString(),
      });
      setCaption("");
      setWhen("");
      await reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao agendar");
    }
  }

  const accLabel = (id: string) => {
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.platform} · ${a.external_account_id}` : id.slice(0, 8);
  };

  if (loading) return <div className="muted">Carregando…</div>;

  return (
    <div>
      <div className="crumb">Social/Ads · Hootsuite</div>
      <div className="toolbar">
        <h1 className="h1" style={{ margin: 0 }}>
          Social/Ads
        </h1>
        <span className="grow" />
        <button className="btn" onClick={connect}>
          + Conectar conta
        </button>
      </div>
      {notice && <div className="notice">{notice}</div>}

      <div className="grid-cards" style={{ marginBottom: 18 }}>
        {accounts.length === 0 && <div className="muted">Nenhuma conta conectada.</div>}
        {accounts.map((a) => (
          <div className="card" key={a.id}>
            <div className="toolbar" style={{ marginBottom: 8 }}>
              <span className="pill cyan">{a.platform}</span>
              <span className="grow" />
              <span className={"pill " + statusPill(a.status)}>
                <span className="dot" /> {a.status}
              </span>
            </div>
            <div className="t ellipsis">{a.external_account_id}</div>
            <div className="mono muted" style={{ fontSize: 12, marginTop: 6 }}>
              {a.scopes.length ? a.scopes.join(", ") : "sem escopos"}
            </div>
          </div>
        ))}
      </div>

      <form className="card" style={{ marginBottom: 18 }} onSubmit={schedule}>
        <h2>Agendar publicação</h2>
        <div className="grid-2">
          <div>
            <label className="muted" style={{ fontSize: 13 }}>
              Conta
            </label>
            <select value={accId} onChange={(e) => setAccId(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.platform} · {a.external_account_id}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="muted" style={{ fontSize: 13 }}>
              Quando
            </label>
            <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          </div>
        </div>
        <label className="muted" style={{ fontSize: 13, display: "block", margin: "12px 0 6px" }}>
          Legenda
        </label>
        <textarea rows={2} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="O que vai postar?" />
        <button className="btn-primary" style={{ marginTop: 14 }} disabled={!accId || !when} type="submit">
          Agendar
        </button>
      </form>

      <div className="card">
        <h2>Fila de publicações</h2>
        {posts.length === 0 && <div className="muted">Nada na fila.</div>}
        {posts.map((p) => (
          <div className="row-item" key={p.id}>
            <span className="grow">
              <span className="t mono ellipsis" style={{ display: "block" }}>
                {accLabel(p.social_account_id)}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                agendado {fmt(p.scheduled_at)} · tentativas {p.attempts}
              </span>
            </span>
            <span className={"pill " + statusPill(p.status)}>
              <span className="dot" /> {p.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
