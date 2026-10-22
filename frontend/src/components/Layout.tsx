import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useJobs } from "./JobsContext";

const NAV = [
  { to: "/", label: "Visão geral", end: true },
  { to: "/trends", label: "Radar de tendências" },
  { to: "/import", label: "Importar vídeos" },
  { to: "/recordings", label: "Gravações e análise" },
  { to: "/candidates", label: "Candidatos a cortes" },
  { to: "/editor", label: "Editor de cortes" },
  { to: "/library", label: "Biblioteca" },
  { to: "/ideas", label: "Ideias e roteiros" },
  { to: "/metrics", label: "Métricas" },
  { to: "/settings", label: "Configurações" },
];

export function Layout() {
  const [open, setOpen] = useState(false);
  const { summary } = useJobs();
  const active = summary ? summary.active.length : 0;

  return (
    <div className="app">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          VALORANT <span>CREATOR</span> STUDIO
        </div>
        <nav aria-label="Navegação principal">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              onClick={() => setOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot small muted">
          <span className="pill">
            <span className={`dot ${active > 0 ? "dot-live" : ""}`} />
            {active > 0 ? `${active} tarefa(s) ativa(s)` : "Nenhuma tarefa ativa"}
          </span>
          <p>Tudo roda no seu computador. Nenhum vídeo é enviado para fora.</p>
        </div>
      </aside>
      <main className="main">
        <button type="button" className="btn menu-toggle" onClick={() => setOpen((o) => !o)}>
          ☰ Menu
        </button>
        <Outlet />
      </main>
    </div>
  );
}
