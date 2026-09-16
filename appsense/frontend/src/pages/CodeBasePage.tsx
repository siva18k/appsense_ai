import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Repo } from "../api";

export function CodeBasePage() {
  const { projectId } = useParams();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"local" | "remote">("local");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load() {
    if (!projectId) return;
    setRepos(await api<Repo[]>(`/api/projects/${projectId}/repos`));
  }

  useEffect(() => {
    load().catch(console.error);
  }, [projectId]);

  async function addRepo(e: FormEvent) {
    e.preventDefault();
    if (!projectId || !location.trim()) return;
    setBusy(true);
    setError("");
    try {
      if (kind === "local") {
        await api(`/api/projects/${projectId}/repos/local`, {
          method: "POST",
          body: JSON.stringify({ name, path: location.trim() }),
        });
      } else {
        await api(`/api/projects/${projectId}/repos/remote`, {
          method: "POST",
          body: JSON.stringify({ name, url: location.trim() }),
        });
      }
      setName("");
      setLocation("");
      setOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add repo");
    } finally {
      setBusy(false);
    }
  }

  async function scan(repo: Repo) {
    if (!projectId) return;
    setScanning(repo.id);
    setError("");
    try {
      await api(`/api/projects/${projectId}/repos/${repo.id}/scan`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(null);
    }
  }

  return (
    <>
      <div className="topbar">
        <h2>Code Base</h2>
        <button className="primary" onClick={() => setOpen(true)}>
          Add repo
        </button>
      </div>
      <div className="page page-wide">
        <p className="lede">
          Link a local folder or Git URL, then Scan. Scan reads the source, writes a markdown
          handbook into Learning, and embeds it for chat RAG alongside the knowledge base.
        </p>
        {error && <p className="muted">{error}</p>}
        <div className="card" style={{ padding: 0, overflow: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Repo name</th>
                <th>URL or local path</th>
                <th>Last scan</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {repos.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted" style={{ padding: 24, textAlign: "center" }}>
                    No repositories yet. Use Add repo, then Scan.
                  </td>
                </tr>
              )}
              {repos.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.name}</strong>
                    <div className="muted">{r.kind}</div>
                  </td>
                  <td className="path-cell">{r.source}</td>
                  <td className="muted">
                    {r.last_scanned_at
                      ? new Date(r.last_scanned_at).toLocaleString()
                      : "Not scanned"}
                  </td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button
                        className="primary"
                        disabled={scanning !== null}
                        onClick={() => scan(r)}
                      >
                        {scanning === r.id ? "Scanning…" : "Scan"}
                      </button>
                      <button
                        className="danger"
                        disabled={scanning !== null}
                        onClick={async () => {
                          await api(`/api/projects/${projectId}/repos/${r.id}`, {
                            method: "DELETE",
                          });
                          await load();
                        }}
                      >
                        Remove
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {open && (
        <div className="modal-backdrop" onClick={() => !busy && setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Add repository</h3>
            <form className="stack" onSubmit={addRepo}>
              <label>Type</label>
              <div className="row">
                <button
                  type="button"
                  className={kind === "local" ? "primary" : "subtle"}
                  onClick={() => setKind("local")}
                >
                  Local path
                </button>
                <button
                  type="button"
                  className={kind === "remote" ? "primary" : "subtle"}
                  onClick={() => setKind("remote")}
                >
                  Git URL
                </button>
              </div>
              <label>Repo name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="payments-api" />
              <label>{kind === "local" ? "Local path" : "Repository URL"}</label>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder={
                  kind === "local" ? "/Users/you/src/my-app" : "https://github.com/org/repo.git"
                }
                required
              />
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <button type="button" className="subtle" onClick={() => setOpen(false)} disabled={busy}>
                  Cancel
                </button>
                <button className="primary" disabled={busy}>
                  {busy ? "Adding…" : "Add repo"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
