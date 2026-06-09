import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="side">
        <div className="logo brandmark">FGOS</div>
        <NavLink to="/" end>
          Dashboard
        </NavLink>
        <NavLink to="/crm">CRM Kanban</NavLink>
        <a href="/dashboard/" target="_blank" rel="noreferrer">
          BI (ECharts) ↗
        </a>
        <div className="spacer" />
        <div className="who mono">
          {user?.email ?? "—"}
          <br />
          <span style={{ opacity: 0.6 }}>{user?.role}</span>
        </div>
        <button className="logout" onClick={logout}>
          Sair
        </button>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
