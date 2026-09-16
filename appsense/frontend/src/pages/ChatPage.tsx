import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import { useParams, useSearchParams } from "react-router-dom";
import {
  api,
  CommandProposal,
  Conversation,
  Message,
  Skill,
  readSse,
} from "../api";

function skillSlug(name: string) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function slashQuery(value: string) {
  if (!value.startsWith("/") || value.includes("\n") || value.includes(" ")) return null;
  return value.slice(1).toLowerCase();
}

type ChatMsg = {
  role: string;
  content: string;
};

export function ChatPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<CommandProposal | null>(null);
  const [cmdOutput, setCmdOutput] = useState("");
  const [running, setRunning] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [slashIndex, setSlashIndex] = useState(0);
  const [mode, setMode] = useState<"chat" | "support">("chat");
  const bottom = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);

  async function loadConversations(select?: string) {
    if (!projectId) return;
    const list = await api<Conversation[]>(`/api/projects/${projectId}/conversations`);
    setConversations(list);
    if (select) setActiveId(select);
  }

  async function openConversation(id: string) {
    if (!projectId) return;
    setActiveId(id);
    const data = await api<{ messages: Message[] }>(
      `/api/projects/${projectId}/conversations/${id}`
    );
    setMessages(
      data.messages.map((m) => ({
        role: m.role,
        content: m.content,
      }))
    );
  }

  async function newChat() {
    if (!projectId) return;
    const conv = await api<Conversation>(`/api/projects/${projectId}/conversations`, {
      method: "POST",
    });
    setActiveId(conv.id);
    setMessages([]);
    setHistoryOpen(false);
    await loadConversations(conv.id);
  }

  useEffect(() => {
    loadConversations().catch(console.error);
    setMessages([]);
    setActiveId(null);
    setHistoryOpen(false);
    setHistoryQuery("");
    setSkills([]);
    if (projectId) {
      api<Skill[]>(`/api/projects/${projectId}/skills`).then(setSkills).catch(console.error);
    }
  }, [projectId]);

  useEffect(() => {
    const skillId = searchParams.get("skill");
    if (!projectId || !skillId) return;
    api<Skill>(`/api/projects/${projectId}/skills/${skillId}`)
      .then((skill) => {
        setInput(`/${skillSlug(skill.name)} `);
        setMode("support");
        setSearchParams({}, { replace: true });
      })
      .catch(console.error);
  }, [projectId, searchParams, setSearchParams]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!historyOpen) return;
    function onPointer(e: MouseEvent) {
      if (historyRef.current && !historyRef.current.contains(e.target as Node)) {
        setHistoryOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setHistoryOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [historyOpen]);

  const slash = mode === "support" ? slashQuery(input) : null;
  const slashMatches = useMemo(() => {
    if (slash === null) return [];
    return skills.filter((s) => {
      const hay = `${s.name} ${skillSlug(s.name)} ${s.goal || ""}`.toLowerCase();
      return slash === "" || hay.includes(slash) || skillSlug(s.name).startsWith(slash);
    });
  }, [skills, slash]);

  useEffect(() => {
    setSlashIndex(0);
  }, [slash]);

  const historyGroups = useMemo(() => {
    const needle = historyQuery.trim().toLowerCase();
    const filtered = needle
      ? conversations.filter((c) => c.title.toLowerCase().includes(needle))
      : conversations;
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const today: Conversation[] = [];
    const earlier: Conversation[] = [];
    for (const c of filtered) {
      if (new Date(c.created_at) >= start) today.push(c);
      else earlier.push(c);
    }
    return [
      { label: "Today", items: today },
      { label: "Earlier", items: earlier },
    ].filter((g) => g.items.length);
  }, [conversations, historyQuery]);

  function applySkill(skill: Skill) {
    setInput(`/${skillSlug(skill.name)} `);
    setSlashIndex(0);
  }

  async function send(e?: FormEvent) {
    e?.preventDefault();
    if (!projectId || !input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setBusy(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: activeId, message: text, mode }),
      });
      if (!res.ok) throw new Error(await res.text());
      await readSse(res, (event) => {
        if (event.type === "conversation" && typeof event.id === "string") {
          setActiveId(event.id);
        }
        if (event.type === "token" && typeof event.text === "string") {
          setMessages((m) => {
            const copy = [...m];
            const last = copy[copy.length - 1];
            if (last?.role === "assistant") {
              copy[copy.length - 1] = { ...last, content: last.content + event.text };
            }
            return copy;
          });
        }
        if (event.type === "command_proposal" && event.command) {
          setProposal(event.command as CommandProposal);
        }
        if (event.type === "error" && typeof event.text === "string") {
          setMessages((m) => {
            const copy = [...m];
            const last = copy[copy.length - 1];
            if (last?.role === "assistant") {
              copy[copy.length - 1] = { ...last, content: last.content + `\n\n${event.text}` };
            }
            return copy;
          });
        }
      });
      await loadConversations();
    } finally {
      setBusy(false);
    }
  }

  async function confirmRun() {
    if (!projectId || !proposal) return;
    setRunning(true);
    setCmdOutput("");
    try {
      const res = await fetch(`/api/projects/${projectId}/commands/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command_id: proposal.id,
          conversation_id: activeId,
        }),
      });
      await readSse(res, (event) => {
        if (event.type === "output" && typeof event.text === "string") {
          setCmdOutput((s) => s + event.text);
        }
        if (event.type === "error" && typeof event.text === "string") {
          setCmdOutput((s) => s + event.text);
        }
      });
    } finally {
      setRunning(false);
      if (activeId) await openConversation(activeId);
    }
  }

  return (
    <div className="chat-wrap">
      <div className="topbar">
        <div className="topbar-left">
          <div className="mode-switch">
            <button
              type="button"
              className={mode === "chat" ? "on" : ""}
              onClick={() => setMode("chat")}
            >
              Chat
            </button>
            <button
              type="button"
              className={mode === "support" ? "on" : ""}
              onClick={() => setMode("support")}
            >
              Support
            </button>
          </div>
          <div className="history-wrap" ref={historyRef}>
            <button
              type="button"
              className="subtle"
              onClick={() => setHistoryOpen((open) => !open)}
            >
              Recents
            </button>
            {historyOpen && (
              <div className="history-panel">
                <input
                  type="search"
                  value={historyQuery}
                  onChange={(e) => setHistoryQuery(e.target.value)}
                  placeholder="Search chats"
                  autoFocus
                />
                <div className="history-scroll">
                  {historyGroups.length === 0 && (
                    <p className="muted" style={{ padding: "8px 10px", margin: 0 }}>
                      {conversations.length === 0 ? "No chats yet" : "No matching chats"}
                    </p>
                  )}
                  {historyGroups.map((group) => (
                    <div key={group.label}>
                      <div className="history-label">{group.label}</div>
                      {group.items.map((c) => (
                        <button
                          type="button"
                          key={c.id}
                          className={c.id === activeId ? "active" : ""}
                          onClick={() => {
                            openConversation(c.id);
                            setHistoryOpen(false);
                            setHistoryQuery("");
                          }}
                        >
                          {c.title}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
        <button className="primary" onClick={newChat}>
          New chat
        </button>
      </div>
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <h3>How can I help with this app?</h3>
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`msg ${m.role}`} key={i}>
            {m.role === "user" ? (
              <div className="bubble">{m.content}</div>
            ) : (
              <div className="markdown">
                <Markdown>{m.content || (busy && i === messages.length - 1 ? "…" : "")}</Markdown>
              </div>
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <form className="composer" onSubmit={send}>
        {slash !== null && (
          <div className="slash-menu">
            <div className="slash-menu-label">Skills</div>
            {slashMatches.length === 0 ? (
              <p className="muted" style={{ margin: 0, padding: "6px 10px" }}>
                {skills.length === 0 ? "No skills yet" : "No matching skill"}
              </p>
            ) : (
              slashMatches.map((s, i) => (
                <button
                  type="button"
                  key={s.id}
                  className={i === slashIndex ? "active" : ""}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    applySkill(s);
                  }}
                >
                  <strong>/{skillSlug(s.name)}</strong>
                  <span>{s.name}</span>
                </button>
              ))
            )}
          </div>
        )}
        <div className="composer-box">
          <textarea
            placeholder={
              mode === "support" ? "Message AppSense…  Type / for skills" : "Message AppSense…"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (slash !== null && slashMatches.length > 0) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setSlashIndex((i) => (i + 1) % slashMatches.length);
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setSlashIndex((i) => (i - 1 + slashMatches.length) % slashMatches.length);
                  return;
                }
                if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
                  e.preventDefault();
                  applySkill(slashMatches[slashIndex]);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setInput("");
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button className="primary" disabled={busy || !input.trim()}>
            Send
          </button>
        </div>
      </form>
      {proposal && (
        <div className="modal-backdrop">
          <div className="modal">
            <h3>Run allowlisted command?</h3>
            <p className="muted">
              {proposal.name}
              {proposal.reason ? ` — ${proposal.reason}` : ""}
            </p>
            <p className="muted">cwd: {proposal.cwd}</p>
            <pre>{proposal.command}</pre>
            {cmdOutput && <pre>{cmdOutput}</pre>}
            <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
              <button className="subtle" onClick={() => setProposal(null)} disabled={running}>
                Cancel
              </button>
              <button className="primary" onClick={confirmRun} disabled={running}>
                {running ? "Running…" : "Confirm run"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
