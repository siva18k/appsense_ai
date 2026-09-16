import { FormEvent, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { BrandMark } from "../components/BrandMark";
import { api, Project } from "../api";

export type ShellContext = {
  projects: Project[];
  reloadProjects: () => Promise<Project[]>;
};

const NAV = [
  { to: "chat", label: "Chat" },
  { to: "learning", label: "Learning" },
  { to: "skills", label: "Skills" },
  { to: "code", label: "Code Base" },
  { to: "knowledge", label: "Knowledge base" },
  { to: "settings", label: "Settings" },
];

export function AppShell() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [openId, setOpenId] = useState<string | undefined>(projectId);

  async function load() {
    const list = await api<Project[]>("/api/projects");
    setProjects(list);
    return list;
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  useEffect(() => {
    if (projectId) setOpenId(projectId);
  }, [projectId]);

  async function addProject(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const created = await api<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name: name.trim(), description: "" }),
    });
    setName("");
    await load();
    setOpenId(created.id);
    navigate(`/projects/${created.id}/chat`);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <BrandMark />
          <div>
            <h1>
              AppSense <span className="brand-ai">ai</span>
            </h1>
            <p>Application support</p>
          </div>
        </div>
        <div className="sidebar-scroll">
          {projects.map((p) => (
            <div className="project-block" key={p.id}>
              <button
                className={`project-head ${openId === p.id ? "active" : ""}`}
                onClick={() => {
                  setOpenId(p.id);
                  navigate(`/projects/${p.id}/chat`);
                }}
              >
                {p.name}
              </button>
              {openId === p.id && (
                <nav className="nav-list">
                  {NAV.map((item) => (
                    <NavLink
                      key={item.to}
                      to={`/projects/${p.id}/${item.to}`}
                      className={({ isActive }) => (isActive ? "active" : "")}
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </nav>
              )}
            </div>
          ))}
        </div>
        <div className="sidebar-footer">
          <form className="project-add" onSubmit={addProject}>
            <input
              placeholder="New project"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button className="ghost" type="submit">
              Add
            </button>
          </form>
          <a className="about-btn" href="/about" target="_blank" rel="noreferrer">
            About
          </a>
        </div>
      </aside>
      <section className="main">
        <Outlet context={{ projects, reloadProjects: load } satisfies ShellContext} />
      </section>
    </div>
  );
}
