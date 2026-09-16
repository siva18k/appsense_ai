import { useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";
import { useParams } from "react-router-dom";
import { AllowCommand, api, KbDoc, LogPath, Repo, Skill } from "../api";

function kindLabel(sourceType: string) {
  if (sourceType === "code_scan") return "Code scan";
  if (sourceType === "pdf") return "PDF";
  if (sourceType === "file") return "File";
  return "Written";
}

function formatWhen(created?: string | null, updated?: string | null) {
  const stamp = updated || created;
  if (!stamp) return "";
  const label = updated && created && updated !== created ? "Updated" : "Created";
  return `${label} ${new Date(stamp).toLocaleString()}`;
}

type Inventory = {
  knowledge: KbDoc[];
  repos: Repo[];
  commands: AllowCommand[];
  logs: LogPath[];
  skills: Skill[];
};

export function LearningPage() {
  const { projectId } = useParams();
  const [inv, setInv] = useState<Inventory | null>(null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState<KbDoc | null>(null);
  const [activeSkill, setActiveSkill] = useState<Skill | null>(null);
  const [busy, setBusy] = useState<"rerag" | "rescan" | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function load() {
    if (!projectId) return;
    const data = await api<Inventory>(`/api/projects/${projectId}/inventory`);
    setInv(data);
    if (active) {
      const still = data.knowledge.find((d) => d.id === active.id);
      if (!still) setActive(null);
    }
  }

  useEffect(() => {
    load().catch(console.error);
    setActive(null);
  }, [projectId]);

  const filtered = useMemo(() => {
    const docs = inv?.knowledge || [];
    const needle = q.trim().toLowerCase();
    if (!needle) return docs;
    return docs.filter((d) =>
      [d.title, d.summary, d.excerpt, d.source_type].join(" ").toLowerCase().includes(needle)
    );
  }, [inv, q]);

  const scans = filtered.filter((d) => d.source_type === "code_scan");
  const notes = filtered.filter((d) => d.source_type !== "code_scan");

  async function open(id: string) {
    if (!projectId) return;
    const doc = await api<KbDoc>(`/api/projects/${projectId}/knowledge/${id}`);
    setActive(doc);
  }

  async function rerag() {
    if (!projectId) return;
    setBusy("rerag");
    setError("");
    try {
      const result = await api<{
        kb_chunks: number;
        code_chunks: number;
        skill_chunks: number;
        repos: number;
      }>(`/api/projects/${projectId}/rerag`, { method: "POST" });
      setStatus(
        `Re-embedded ${result.kb_chunks} knowledge chunks, ${result.code_chunks} code chunks, and ${result.skill_chunks} skill chunks.`
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-RAG failed");
    } finally {
      setBusy(null);
    }
  }

  async function rescan() {
    if (!projectId) return;
    setBusy("rescan");
    setError("");
    try {
      const result = await api<{ repos: number; files_read: number }>(
        `/api/projects/${projectId}/rescan`,
        { method: "POST" }
      );
      setStatus(`Re-scanned ${result.repos} repos (${result.files_read} files) and refreshed learning docs.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-scan failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="topbar">
        <h2>Learning</h2>
        <div className="row">
          <button className="subtle" disabled={busy !== null} onClick={rerag}>
            {busy === "rerag" ? "Re-RAG…" : "Re-RAG embeddings"}
          </button>
          <button className="primary" disabled={busy !== null} onClick={rescan}>
            {busy === "rescan" ? "Scanning…" : "Re-scan code"}
          </button>
        </div>
      </div>
      <div className="page page-wide">
        <p className="lede">
          Everything Chat can use: knowledge cards, scanned code handbooks, linked repos, allowlisted
          commands, and log paths.
        </p>
        {status && <p className="muted">{status}</p>}
        {error && <p className="muted">{error}</p>}
        <input
          type="text"
          placeholder="Search knowledge and scans"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ marginBottom: 16 }}
        />

        <div className="learn-layout">
          <div className="learn-list">
            <section className="learn-section">
              <h3>Knowledge ({notes.length})</h3>
              {notes.length === 0 && <p className="muted">No written or uploaded knowledge yet.</p>}
              {notes.map((d) => (
                <button
                  type="button"
                  key={d.id}
                  className={active?.id === d.id ? "active" : ""}
                  onClick={() => {
                    setActiveSkill(null);
                    setActive({ ...d, body: d.body || d.excerpt || "" });
                    open(d.id);
                  }}
                >
                  <strong>{d.title}</strong>
                  <div className="muted">
                    {kindLabel(d.source_type)} · {d.summary || d.excerpt || "No summary"}
                  </div>
                  <div className="muted">{formatWhen(d.created_at, d.updated_at)}</div>
                </button>
              ))}
            </section>
            <section className="learn-section">
              <h3>Code scans ({scans.length})</h3>
              {scans.length === 0 && <p className="muted">Scan a repo in Code Base to add a handbook.</p>}
              {scans.map((d) => (
                <button
                  type="button"
                  key={d.id}
                  className={active?.id === d.id ? "active" : ""}
                  onClick={() => {
                    setActiveSkill(null);
                    setActive({ ...d, body: d.body || d.excerpt || "" });
                    open(d.id);
                  }}
                >
                  <strong>{d.title}</strong>
                  <div className="muted">{d.summary || d.excerpt || "No summary"}</div>
                  <div className="muted">{formatWhen(d.created_at, d.updated_at)}</div>
                </button>
              ))}
            </section>
            <section className="learn-section">
              <h3>Repositories ({inv?.repos.length || 0})</h3>
              {(inv?.repos || []).map((r) => (
                <div className="learn-meta" key={r.id}>
                  <strong>{r.name}</strong>
                  <div className="muted">{r.source}</div>
                  <div className="muted">
                    {r.last_scanned_at
                      ? `Scanned ${new Date(r.last_scanned_at).toLocaleString()}`
                      : "Not scanned"}
                    {r.last_indexed_at
                      ? ` · Indexed ${new Date(r.last_indexed_at).toLocaleString()}`
                      : ""}
                  </div>
                </div>
              ))}
            </section>
            <section className="learn-section">
              <h3>Skills ({inv?.skills.length || 0})</h3>
              {(inv?.skills || []).map((s) => (
                <button
                  type="button"
                  key={s.id}
                  className={activeSkill?.id === s.id ? "active" : ""}
                  onClick={async () => {
                    setActive(null);
                    if (!projectId) return;
                    const full = await api<Skill>(`/api/projects/${projectId}/skills/${s.id}`);
                    setActiveSkill(full);
                  }}
                >
                  <strong>{s.name}</strong>
                  <div className="muted">{s.refined ? "AI-refined" : "As written"} · {s.summary || s.goal}</div>
                </button>
              ))}
              {(inv?.skills || []).length === 0 && (
                <p className="muted">None yet — add them under Skills.</p>
              )}
            </section>
            <section className="learn-section">
              <h3>Allowlisted commands ({inv?.commands.length || 0})</h3>
              {(inv?.commands || []).map((c) => (
                <div className="learn-meta" key={c.id}>
                  <strong>{c.name}</strong>
                  <div className="muted">{c.description || c.command}</div>
                </div>
              ))}
              {(inv?.commands || []).length === 0 && (
                <p className="muted">None yet — add them in Settings.</p>
              )}
            </section>
            <section className="learn-section">
              <h3>Log paths ({inv?.logs.length || 0})</h3>
              {(inv?.logs || []).map((l) => (
                <div className="learn-meta" key={l.id}>
                  <strong>{l.label}</strong>
                  <div className="muted">{l.path}</div>
                </div>
              ))}
              {(inv?.logs || []).length === 0 && <p className="muted">None yet — add them in Settings.</p>}
            </section>
          </div>
          <div className="card learn-reader">
            {activeSkill ? (
              <>
                <h3 style={{ marginTop: 0 }}>{activeSkill.name}</h3>
                <p className="muted">{activeSkill.refined ? "AI-refined skill" : "Saved as written"}</p>
                <div className="markdown markdown-article">
                  <Markdown>{activeSkill.body || activeSkill.goal}</Markdown>
                </div>
              </>
            ) : active ? (
              <>
                <h3 style={{ marginTop: 0 }}>{active.title}</h3>
                <p className="muted">
                  {kindLabel(active.source_type)} · {formatWhen(active.created_at, active.updated_at)}
                </p>
                <div className="markdown markdown-article">
                  <Markdown>{active.body || ""}</Markdown>
                </div>
              </>
            ) : (
              <p className="muted">Select knowledge, a code scan, or a skill to preview.</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
