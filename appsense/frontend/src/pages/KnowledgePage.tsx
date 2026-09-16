import { FormEvent, useEffect, useState } from "react";
import Markdown from "react-markdown";
import { useParams } from "react-router-dom";
import { api, KbDoc } from "../api";

function formatWhen(created?: string | null, updated?: string | null) {
  const c = created ? new Date(created) : null;
  const u = updated ? new Date(updated) : null;
  if (u && c && u.getTime() - c.getTime() > 2000) {
    return `Updated ${u.toLocaleString()}`;
  }
  if (c) return `Created ${c.toLocaleString()}`;
  return "";
}

function typeLabel(doc: KbDoc) {
  if (doc.source_type === "pdf") return "PDF";
  if (doc.source_type === "file") return "File";
  return "Written";
}

export function KnowledgePage() {
  const { projectId } = useParams();
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const [mode, setMode] = useState<"write" | "upload">("write");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [fileTitle, setFileTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  const [replaceFile, setReplaceFile] = useState<File | null>(null);
  const [error, setError] = useState("");

  async function load() {
    if (!projectId) return;
    setDocs(await api<KbDoc[]>(`/api/projects/${projectId}/knowledge?kind=uploads`));
  }

  useEffect(() => {
    load().catch(console.error);
  }, [projectId]);

  async function addWritten(e: FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/projects/${projectId}/knowledge/text`, {
        method: "POST",
        body: JSON.stringify({ title, body }),
      });
      setTitle("");
      setBody("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  async function addUpload(e: FormEvent) {
    e.preventDefault();
    if (!projectId || !file) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("title", fileTitle);
      fd.append("file", file);
      const res = await fetch(`/api/projects/${projectId}/knowledge/upload`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      setFileTitle("");
      setFile(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggleExpand(id: string) {
    if (expanded === id) {
      setExpanded(null);
      setEditing(null);
      return;
    }
    if (!projectId) return;
    const doc = await api<KbDoc>(`/api/projects/${projectId}/knowledge/${id}`);
    setDocs((list) => list.map((d) => (d.id === id ? { ...d, ...doc } : d)));
    setExpanded(id);
    setEditing(null);
    setReplaceFile(null);
  }

  async function saveEdit(id: string) {
    if (!projectId) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/knowledge/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: editTitle, body: editBody }),
      });
      setEditing(null);
      await load();
      const doc = await api<KbDoc>(`/api/projects/${projectId}/knowledge/${id}`);
      setDocs((list) => list.map((d) => (d.id === id ? { ...d, ...doc } : d)));
    } finally {
      setBusy(false);
    }
  }

  async function saveReplace(id: string, currentTitle: string) {
    if (!projectId || !replaceFile) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("title", currentTitle);
      fd.append("file", replaceFile);
      const res = await fetch(`/api/projects/${projectId}/knowledge/${id}/upload`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      setReplaceFile(null);
      await load();
      const doc = await api<KbDoc>(`/api/projects/${projectId}/knowledge/${id}`);
      setDocs((list) => list.map((d) => (d.id === id ? { ...d, ...doc } : d)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="topbar">
        <h2>Knowledge base</h2>
      </div>
      <div className="page page-wide">
        <p className="lede">
          Write a note or upload a PDF or text file. Each item is a card you can expand, edit, or
          replace. Chat and Learning use the embedded text.
        </p>
        {error && <p className="muted">{error}</p>}

        <div className="card kb-composer">
          <div className="row" style={{ marginBottom: 12 }}>
            <button
              type="button"
              className={mode === "write" ? "primary" : "subtle"}
              onClick={() => setMode("write")}
            >
              Write
            </button>
            <button
              type="button"
              className={mode === "upload" ? "primary" : "subtle"}
              onClick={() => setMode("upload")}
            >
              Upload
            </button>
          </div>
          {mode === "write" ? (
            <form className="stack" onSubmit={addWritten}>
              <label>Name</label>
              <input
                className="title-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="How to restart the API"
                required
              />
              <label>Content</label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Paste or type the knowledge…"
                required
              />
              <button className="primary" disabled={busy}>
                Add knowledge
              </button>
            </form>
          ) : (
            <form className="stack" onSubmit={addUpload}>
              <label>Name (optional)</label>
              <input
                className="title-input"
                value={fileTitle}
                onChange={(e) => setFileTitle(e.target.value)}
                placeholder="Defaults to the file name"
              />
              <label>PDF or text file</label>
              <label className="file-field">
                <input
                  type="file"
                  accept=".pdf,.txt,.md,.markdown,.text,.log"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
                <span className="file-field-btn">Choose file</span>
                <span className="file-field-name">{file ? file.name : "No file chosen"}</span>
              </label>
              <button className="primary" disabled={busy || !file}>
                Upload knowledge
              </button>
            </form>
          )}
        </div>

        <div className="kb-list">
          {docs.length === 0 && (
            <div className="empty">
              <h3>No knowledge yet</h3>
              <p>Add a written note or upload a file above.</p>
            </div>
          )}
          {docs.map((d) => {
            const open = expanded === d.id;
            const summary = d.summary || d.excerpt || "";
            const isWritten = d.source_type === "text";
            return (
              <article className={`kb-card ${open ? "open" : ""}`} key={d.id}>
                <div className="kb-card-main">
                  <div className="kb-card-copy">
                    <h3>{d.title}</h3>
                    <p className="kb-summary">{summary || "No summary yet."}</p>
                    <div className="muted">
                      {typeLabel(d)}
                      {d.filename ? ` · ${d.filename}` : ""}
                      {" · "}
                      {formatWhen(d.created_at, d.updated_at)}
                    </div>
                  </div>
                  <div className="kb-card-actions">
                    <button className="subtle" onClick={() => toggleExpand(d.id)}>
                      {open ? "Collapse" : "Expand"}
                    </button>
                    <button
                      className="danger"
                      onClick={async () => {
                        await api(`/api/projects/${projectId}/knowledge/${d.id}`, {
                          method: "DELETE",
                        });
                        if (expanded === d.id) setExpanded(null);
                        await load();
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {open && (
                  <div className="kb-card-preview">
                    {editing === d.id && isWritten ? (
                      <div className="stack">
                        <label>Name</label>
                        <input
                          className="title-input"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                        />
                        <label>Content</label>
                        <textarea
                          value={editBody}
                          onChange={(e) => setEditBody(e.target.value)}
                          style={{ minHeight: 220 }}
                        />
                        <div className="row">
                          <button className="primary" disabled={busy} onClick={() => saveEdit(d.id)}>
                            Save changes
                          </button>
                          <button className="subtle" onClick={() => setEditing(null)}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="markdown markdown-article">
                          <Markdown>{d.body || ""}</Markdown>
                        </div>
                        {isWritten ? (
                          <button
                            className="primary"
                            onClick={() => {
                              setEditing(d.id);
                              setEditTitle(d.title);
                              setEditBody(d.body || "");
                            }}
                          >
                            Edit
                          </button>
                        ) : (
                          <div className="stack" style={{ marginTop: 12 }}>
                            <label>Re-upload PDF or text file</label>
                            <label className="file-field">
                              <input
                                type="file"
                                accept=".pdf,.txt,.md,.markdown,.text,.log"
                                onChange={(e) => setReplaceFile(e.target.files?.[0] || null)}
                              />
                              <span className="file-field-btn">Choose file</span>
                              <span className="file-field-name">
                                {replaceFile ? replaceFile.name : "No file chosen"}
                              </span>
                            </label>
                            <button
                              className="primary"
                              disabled={busy || !replaceFile}
                              onClick={() => saveReplace(d.id, d.title)}
                            >
                              Replace file
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </>
  );
}
