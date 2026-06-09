import { useEffect, useState } from "react";
import { api, type Item, type ListRow } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Workspace() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [lists, setLists] = useState<ListRow[]>([]);
  const [activeList, setActiveList] = useState<ListRow | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const wss = await api.workspaces(agencyId);
        if (!alive) return;
        if (wss.length === 0) {
          setNotice("Nenhum workspace. Rode `fgos seed` ou crie uma agência no onboarding.");
          setLoading(false);
          return;
        }
        const ls = await api.lists(wss[0].id);
        if (!alive) return;
        setLists(ls);
        if (ls.length > 0) {
          setActiveList(ls[0]);
          setItems(await api.items(ls[0].id));
        }
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

  async function selectList(l: ListRow) {
    setActiveList(l);
    setItems([]);
    try {
      setItems(await api.items(l.id));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "erro");
    }
  }

  async function addItem() {
    if (!activeList) return;
    const title = prompt("Título da tarefa:");
    if (!title) return;
    try {
      await api.createItem({ list_id: activeList.id, agency_id: agencyId, title });
      setItems(await api.items(activeList.id));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "falha ao criar");
    }
  }

  const statusClass = (s: string) =>
    s === "done" ? "green" : s === "open" ? "cyan" : "amber";

  if (loading) return <div className="muted">Carregando…</div>;

  return (
    <div>
      <div className="crumb">Produtividade · ClickUp/Monday</div>
      <div className="toolbar">
        <h1 className="h1" style={{ margin: 0 }}>
          Workspace
        </h1>
        <span className="grow" />
        <button className="btn-primary" onClick={addItem} disabled={!activeList}>
          + Tarefa
        </button>
      </div>
      {notice && <div className="notice">{notice}</div>}

      <div className="grid-2">
        <div className="card">
          <h2>Listas</h2>
          {lists.length === 0 && <div className="muted">Sem listas.</div>}
          {lists.map((l) => (
            <button
              key={l.id}
              className={"sess" + (activeList?.id === l.id ? " active" : "")}
              onClick={() => selectList(l)}
            >
              <div className="top">
                <span className="nm">{l.name}</span>
                <span className="pill">{l.item_count}</span>
              </div>
            </button>
          ))}
        </div>

        <div className="card">
          <h2>{activeList ? `Itens · ${activeList.name}` : "Itens"}</h2>
          {items.length === 0 && <div className="muted">Nenhum item nesta lista.</div>}
          {items.map((it) => (
            <div className="row-item" key={it.id}>
              <span className={"dot pill " + statusClass(it.status)} style={{ padding: 0, width: 8, height: 8, border: 0 }} />
              <span className="grow t ellipsis">{it.title}</span>
              <span className={"pill " + statusClass(it.status)}>{it.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
