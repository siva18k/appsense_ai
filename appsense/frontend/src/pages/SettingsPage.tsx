import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api, AllowCommand, LogPath, Project, Settings } from "../api";
import { ShellContext } from "../layout/AppShell";

export function SettingsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { projects, reloadProjects } = useOutletContext<ShellContext>();
  const project = projects.find((p: Project) => p.id === projectId);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [llmBase, setLlmBase] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [embed, setEmbed] = useState("");
  const [chroma, setChroma] = useState("");
  const [saved, setSaved] = useState("");
  const [commands, setCommands] = useState<AllowCommand[]>([]);
  const [logs, setLogs] = useState<LogPath[]>([]);
  const [cmd, setCmd] = useState({ name: "", description: "", cwd: "", command: "" });
  const [log, setLog] = useState({ label: "", path: "" });
  const [confirmName, setConfirmName] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  async function load() {
    const s = await api<Settings>("/api/settings");
    setSettings(s);
    setLlmBase(s.llm_base_url);
    setLlmModel(s.llm_model);
    setEmbed(s.embedding_model);
    setChroma(s.chroma_path);
    if (projectId) {
      setCommands(await api<AllowCommand[]>(`/api/projects/${projectId}/commands`));
      setLogs(await api<LogPath[]>(`/api/projects/${projectId}/logs`));
    }
  }

  useEffect(() => {
    load().catch(console.error);
  }, [projectId]);

  async function saveGlobal(e: FormEvent) {
    e.preventDefault();
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        llm_base_url: llmBase,
        llm_model: llmModel,
        llm_api_key: apiKey,
        embedding_model: embed,
        chroma_path: chroma,
      }),
    });
    setApiKey("");
    setSaved("Saved to local .env");
    await load();
  }

  async function addCommand(e: FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    await api(`/api/projects/${projectId}/commands`, {
      method: "POST",
      body: JSON.stringify(cmd),
    });
    setCmd({ name: "", description: "", cwd: "", command: "" });
    await load();
  }

  async function addLog(e: FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    await api(`/api/projects/${projectId}/logs`, {
      method: "POST",
      body: JSON.stringify(log),
    });
    setLog({ label: "", path: "" });
    await load();
  }

  return (
    <>
      <div className="topbar">
        <h2>Settings</h2>
      </div>
      <div className="page page-wide">
        <p className="lede">
          API keys are stored in <code>{settings?.env_path}</code> and are never shown after save.
        </p>
        <form className="card stack" onSubmit={saveGlobal}>
          <h3 style={{ marginTop: 0 }}>LLM and RAG</h3>
          <label>LLM base URL (Mistral: https://api.mistral.ai/v1)</label>
          <input value={llmBase} onChange={(e) => setLlmBase(e.target.value)} />
          <label>Model</label>
          <input value={llmModel} onChange={(e) => setLlmModel(e.target.value)} />
          <label>API key {settings?.has_api_key ? "(set — leave blank to keep)" : "(not set)"}</label>
          <input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings?.has_api_key ? "••••••••" : ""}
          />
          <label>Embedding model (mistral-embed uses your LLM key)</label>
          <input value={embed} onChange={(e) => setEmbed(e.target.value)} />
          <label>Chroma path</label>
          <input value={chroma} onChange={(e) => setChroma(e.target.value)} />
          <div className="row">
            <button className="primary">Save</button>
            {saved && <span className="muted">{saved}</span>}
            <span className="muted">
              <span className={`status-dot ${settings?.has_api_key ? "" : "off"}`} />
              LLM key
            </span>
          </div>
        </form>

        <form className="card stack" onSubmit={addLog}>
          <h3 style={{ marginTop: 0 }}>Application logs</h3>
          <p className="muted">Chat may only read these paths.</p>
          <div className="log-add-row">
            <input
              value={log.label}
              onChange={(e) => setLog({ ...log, label: e.target.value })}
              placeholder="Label"
              required
            />
            <input
              value={log.path}
              onChange={(e) => setLog({ ...log, path: e.target.value })}
              placeholder="Path"
              required
            />
            <button className="primary">Add</button>
          </div>
          {logs.map((l) => (
            <div className="item" key={l.id}>
              <div>
                <strong>{l.label}</strong>
                <div className="muted">{l.path}</div>
              </div>
              <button
                type="button"
                className="danger"
                onClick={async () => {
                  await api(`/api/projects/${projectId}/logs/${l.id}`, { method: "DELETE" });
                  await load();
                }}
              >
                Remove
              </button>
            </div>
          ))}
        </form>

        <form className="card stack" onSubmit={addCommand}>
          <h3 style={{ marginTop: 0 }}>Allowlisted commands</h3>
          <p className="muted">
            Chat can propose these only. They run after you press Confirm — never as free-form
            shell.
          </p>
          <label>Name</label>
          <input
            value={cmd.name}
            onChange={(e) => setCmd({ ...cmd, name: e.target.value })}
            placeholder="restart-api"
            required
          />
          <label>Description</label>
          <input
            value={cmd.description}
            onChange={(e) => setCmd({ ...cmd, description: e.target.value })}
          />
          <label>Working directory</label>
          <input
            value={cmd.cwd}
            onChange={(e) => setCmd({ ...cmd, cwd: e.target.value })}
            required
          />
          <label>Command</label>
          <input
            value={cmd.command}
            onChange={(e) => setCmd({ ...cmd, command: e.target.value })}
            placeholder="echo hello"
            required
          />
          <button className="primary">Add command</button>
          {commands.map((c) => (
            <div className="item" key={c.id}>
              <div>
                <strong>{c.name}</strong>
                <div className="muted">{c.description}</div>
                <div className="muted">
                  {c.cwd} · {c.command}
                </div>
              </div>
              <button
                type="button"
                className="danger"
                onClick={async () => {
                  await api(`/api/projects/${projectId}/commands/${c.id}`, { method: "DELETE" });
                  await load();
                }}
              >
                Remove
              </button>
            </div>
          ))}
        </form>

        <div className="card stack danger-zone">
          <h3 style={{ marginTop: 0 }}>Delete this project</h3>
          <p className="muted">
            Permanently removes {project?.name || "this project"} including chat, knowledge, skills,
            linked repos, commands, and log paths. This cannot be undone.
          </p>
          <label>Type the project name to confirm</label>
          <input
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder={project?.name || "Project name"}
          />
          {deleteError && <p className="muted">{deleteError}</p>}
          <button
            type="button"
            className="danger-solid"
            disabled={
              deleting || !projectId || !project || confirmName.trim() !== project.name
            }
            onClick={async () => {
              if (!projectId || !project) return;
              setDeleting(true);
              setDeleteError("");
              try {
                await api(`/api/projects/${projectId}`, { method: "DELETE" });
                const remaining = (await reloadProjects()).filter((p) => p.id !== projectId);
                setConfirmName("");
                if (remaining[0]) {
                  navigate(`/projects/${remaining[0].id}/chat`);
                } else {
                  navigate("/");
                }
              } catch (err) {
                setDeleteError(err instanceof Error ? err.message : "Could not delete project");
              } finally {
                setDeleting(false);
              }
            }}
          >
            {deleting ? "Deleting…" : "Delete entire project"}
          </button>
        </div>
      </div>
    </>
  );
}
