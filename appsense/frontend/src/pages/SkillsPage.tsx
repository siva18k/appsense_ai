import { FormEvent, useEffect, useState } from "react";
import Markdown from "react-markdown";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

export type Skill = {
  id: string;
  project_id: string;
  name: string;
  goal: string;
  body: string;
  refined: boolean;
  summary?: string;
  excerpt?: string;
  created_at: string;
  updated_at: string;
};

export function SkillsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [draft, setDraft] = useState("");
  const [refined, setRefined] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editing, setEditing] = useState<Skill | null>(null);

  async function load() {
    if (!projectId) return;
    setSkills(await api<Skill[]>(`/api/projects/${projectId}/skills`));
  }

  useEffect(() => {
    load().catch(console.error);
    setEditing(null);
    setExpanded(null);
  }, [projectId]);

  async function refine(e?: FormEvent) {
    e?.preventDefault();
    if (!projectId || !goal.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ markdown: string }>(`/api/projects/${projectId}/skills/refine`, {
        method: "POST",
        body: JSON.stringify({ name, goal }),
      });
      setDraft(result.markdown);
      setRefined(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refine failed");
    } finally {
      setBusy(false);
    }
  }

  async function save(useDraft: boolean) {
    if (!projectId || !goal.trim()) return;
    setBusy(true);
    setError("");
    try {
      const body = useDraft && draft.trim() ? draft : goal;
      await api(`/api/projects/${projectId}/skills`, {
        method: "POST",
        body: JSON.stringify({
          name,
          goal,
          body,
          refined: useDraft && refined,
        }),
      });
      setName("");
      setGoal("");
      setDraft("");
      setRefined(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    if (!projectId || !editing) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/skills/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: editing.name,
          goal: editing.goal,
          body: editing.body,
          refined: editing.refined,
        }),
      });
      setEditing(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function refineExisting(skill: Skill) {
    if (!projectId) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ markdown: string }>(`/api/projects/${projectId}/skills/refine`, {
        method: "POST",
        body: JSON.stringify({ name: skill.name, goal: skill.goal || skill.body }),
      });
      setEditing({ ...skill, body: result.markdown, refined: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refine failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="topbar">
        <h2>Skills</h2>
      </div>
      <div className="page page-wide">
        <p className="lede">
          Describe a multi-step agent task (report, batch job, email, restart, and so on). Save it as
          written, or optionally Refine with AI so it becomes a detailed markdown playbook using this
          app’s knowledge, code, and allowlisted commands.
        </p>
        {error && <p className="muted">{error}</p>}

        <div className="card kb-composer">
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              save(false);
            }}
          >
            <label>Skill name</label>
            <input
              className="title-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Nightly settlement check"
            />
            <label>What should this skill do?</label>
            <textarea
              value={goal}
              onChange={(e) => {
                setGoal(e.target.value);
                if (!refined) setDraft("");
              }}
              placeholder="e.g. Check yesterday’s batch, summarize failures from the log, and propose the allowlisted restart if it died."
              required
            />
            {draft && (
              <>
                <label>Refined playbook (editable before save)</label>
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  style={{ minHeight: 260 }}
                />
                <p className="muted">
                  You can still save the original wording instead of this refined markdown.
                </p>
              </>
            )}
            <div className="row" style={{ flexWrap: "wrap" }}>
              <button type="button" className="subtle" disabled={busy || !goal.trim()} onClick={refine}>
                {busy ? "Working…" : "Refine with AI"}
              </button>
              {draft ? (
                <>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy}
                    onClick={() => save(true)}
                  >
                    Save refined skill
                  </button>
                  <button type="button" className="subtle" disabled={busy} onClick={() => save(false)}>
                    Save original only
                  </button>
                  <button
                    type="button"
                    className="subtle"
                    onClick={() => {
                      setDraft("");
                      setRefined(false);
                    }}
                  >
                    Discard refine
                  </button>
                </>
              ) : (
                <button className="primary" disabled={busy || !goal.trim()}>
                  Save without AI
                </button>
              )}
            </div>
          </form>
        </div>

        <div className="kb-list">
          {skills.length === 0 && (
            <div className="empty">
              <h3>No skills yet</h3>
              <p>Add a task description above. Refine with AI is optional.</p>
            </div>
          )}
          {skills.map((s) => {
            const open = expanded === s.id;
            const current = editing?.id === s.id ? editing : s;
            return (
              <article className={`kb-card ${open ? "open" : ""}`} key={s.id}>
                <div className="kb-card-main">
                  <div className="kb-card-copy">
                    <h3>{s.name}</h3>
                    <p className="kb-summary">{s.summary || s.goal}</p>
                    <div className="muted">
                      {s.refined ? "AI-refined playbook" : "Saved as written"}
                      {" · "}
                      Updated {new Date(s.updated_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="kb-card-actions">
                    <button
                      className="subtle"
                      onClick={async () => {
                        if (open) {
                          setExpanded(null);
                          setEditing(null);
                          return;
                        }
                        const full = await api<Skill>(`/api/projects/${projectId}/skills/${s.id}`);
                        setEditing(full);
                        setExpanded(s.id);
                      }}
                    >
                      {open ? "Collapse" : "Expand"}
                    </button>
                    <button
                      className="primary"
                      onClick={() => navigate(`/projects/${projectId}/chat?skill=${s.id}`)}
                    >
                      Use in chat
                    </button>
                    <button
                      className="danger"
                      onClick={async () => {
                        await api(`/api/projects/${projectId}/skills/${s.id}`, { method: "DELETE" });
                        if (expanded === s.id) setExpanded(null);
                        await load();
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {open && current && (
                  <div className="kb-card-preview">
                    <div className="stack">
                      <label>Name</label>
                      <input
                        className="title-input"
                        value={current.name}
                        onChange={(e) => setEditing({ ...current, name: e.target.value })}
                      />
                      <label>Original idea</label>
                      <textarea
                        value={current.goal}
                        onChange={(e) => setEditing({ ...current, goal: e.target.value })}
                        style={{ minHeight: 100 }}
                      />
                      <label>Playbook</label>
                      <textarea
                        value={current.body}
                        onChange={(e) => setEditing({ ...current, body: e.target.value })}
                        style={{ minHeight: 240 }}
                      />
                      <div className="markdown markdown-article">
                        <Markdown>{current.body}</Markdown>
                      </div>
                      <div className="row" style={{ flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="subtle"
                          disabled={busy}
                          onClick={() => refineExisting(current)}
                        >
                          Refine with AI
                        </button>
                        <button type="button" className="primary" disabled={busy} onClick={saveEdit}>
                          Save
                        </button>
                      </div>
                    </div>
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
