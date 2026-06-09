import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";

const NAV: Array<[string, string, string]> = [
  ["/", "▣", "Dashboard"],
  ["/crm", "⊞", "CRM Kanban"],
  ["/chat", "✦", "Mensageria"],
  ["/social", "◈", "Social/Ads"],
  ["/workspace", "☰", "Workspace"],
];

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const loc = useLocation();

  return (
    <div className="shell">
      <header className="topbar">
        <button className="burger" onClick={() => setOpen(true)} aria-label="menu">
          ☰
        </button>
        <span className="brandmark">FGOS</span>
      </header>

      <div className={"scrim" + (open ? " show" : "")} onClick={() => setOpen(false)} />

      <aside className={"side" + (open ? " open" : "")}>
        <div className="logo brandmark">FGOS</div>
        <div className="tag">FAT TECH · OPERAÇÃO</div>
        {NAV.map(([to, ico, label]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => "navlink" + (isActive ? " active" : "")}
            onClick={() => setOpen(false)}
          >
            <span className="ico">{ico}</span>
            {label}
          </NavLink>
        ))}
        <a className="navlink" href="/dashboard/" target="_blank" rel="noreferrer">
          <span className="ico">↗</span> BI (ECharts)
        </a>

        <div className="spacer" />
        <div className="who">
          <b>{user?.email ?? "—"}</b>
          <br />
          <span className="mono" style={{ opacity: 0.6 }}>
            {user?.role}
          </span>
        </div>
        <button className="logout" onClick={logout}>
          Sair
        </button>
      </aside>

      <main className="main" key={loc.pathname}>
        <Outlet />
      </main>
    </div>
  );
}
