import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";
import { useParams, useSearchParams } from "react-router-dom";
import {
  api,
  AllowCommand,
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

function commandQuery(value: string) {
  if (!value.startsWith("@") || value.includes("\n") || value.includes(" ")) return null;
  return value.slice(1).toLowerCase();
}

type ChatMsg = {
  role: string;
  content: string;
};

type MarkdownCodeProps = {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
};

function codeText(children: ReactNode) {
  return String(children ?? "").replace(/\n$/, "");
}

function StructuredArtifact({ language, source }: { language: string; source: string }) {
  const normalized = language.toLowerCase();
  if (normalized === "html" || normalized === "htm") {
    return (
      <div className="chat-artifact">
        <div className="chat-artifact-label">html preview</div>
        <iframe className="html-preview" title="HTML response preview" sandbox="" srcDoc={source} />
        <details><summary>view source</summary><pre>{source}</pre></details>
      </div>
    );
  }
  if (normalized === "json" || normalized === "jsonc") {
    let formatted = source;
    try { formatted = JSON.stringify(JSON.parse(source), null, 2); } catch { /* keep source */ }
    return <div className="chat-artifact"><div className="chat-artifact-label">json</div><pre>{formatted}</pre></div>;
  }
  if (normalized === "drawio" || normalized === "mxfile" || (normalized === "xml" && source.includes("<mxfile"))) {
    return (
      <div className="chat-artifact">
        <div className="chat-artifact-label">draw.io diagram source</div>
        <p className="muted">This response contains draw.io XML. Download or import the source in diagrams.net to edit the diagram.</p>
        <pre>{source}</pre>
      </div>
    );
  }
  if (normalized === "mermaid") {
    return <div className="chat-artifact"><div className="chat-artifact-label">diagram definition</div><pre>{source}</pre><p className="muted">Mermaid rendering can be enabled when the diagram package is added.</p></div>;
  }
  return <pre><code>{source}</code></pre>;
}

function MarkdownCode({ inline, className, children }: MarkdownCodeProps) {
  const source = codeText(children);
  const language = className?.match(/language-(\w+)/)?.[1];
  if (inline || !language) return <code>{children}</code>;
  return <StructuredArtifact language={language} source={source} />;
}

type ChatRuntime = {
  activeId: string | null;
  messages: ChatMsg[];
  proposal: CommandProposal | null;
  actionRequest: string;
  cmdOutput: string;
  cmdSummary: string;
  activity: string;
  busy: boolean;
  running: boolean;
};

function runtimeKey(projectId: string) {
  return `appsense-chat-runtime:${projectId}`;
}

function readRuntime(projectId?: string): ChatRuntime | null {
  if (!projectId) return null;
  try {
    const raw = localStorage.getItem(runtimeKey(projectId));
    return raw ? JSON.parse(raw) as ChatRuntime : null;
  } catch {
    return null;
  }
}

function writeRuntime(projectId: string | undefined, runtime: Partial<ChatRuntime>) {
  if (!projectId) return;
  const current = readRuntime(projectId) || {
    activeId: null,
    messages: [],
    proposal: null,
    actionRequest: "",
    cmdOutput: "",
    cmdSummary: "",
    activity: "",
    busy: false,
    running: false,
  };
  localStorage.setItem(runtimeKey(projectId), JSON.stringify({ ...current, ...runtime }));
}

function clearRuntime(projectId?: string) {
  if (projectId) localStorage.removeItem(runtimeKey(projectId));
}

export function ChatPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState("");
  const [proposal, setProposal] = useState<CommandProposal | null>(null);
  const [actionRequest, setActionRequest] = useState("");
  const [activeSkillRun, setActiveSkillRun] = useState(false);
  const [cmdOutput, setCmdOutput] = useState("");
  const [cmdSummary, setCmdSummary] = useState("");
  const [running, setRunning] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [clearBusy, setClearBusy] = useState(false);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [commands, setCommands] = useState<AllowCommand[]>([]);
  const [slashIndex, setSlashIndex] = useState(0);
  const [commandIndex, setCommandIndex] = useState(0);
  const [mode, setMode] = useState<"chat" | "support">("chat");
  const bottom = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const actionController = useRef<AbortController | null>(null);

  function stopAction() {
    actionController.current?.abort();
    actionController.current = null;
    setBusy(false);
    setRunning(false);
    setActivity("");
  }

  function showAssistant(text: string, onlyIfEmpty = false) {
    setMessages((current) => {
      const copy = [...current];
      const last = copy[copy.length - 1];
      if (last?.role === "assistant") {
        if (!last.content.trim()) {
          copy[copy.length - 1] = { ...last, content: text };
          return copy;
        }
        if (onlyIfEmpty) return copy;
      }
      return [...copy, { role: "assistant", content: text }];
    });
  }

  async function loadConversations(select?: string) {
    if (!projectId) return;
    const list = await api<Conversation[]>(`/api/projects/${projectId}/conversations`);
    setConversations(list);
    setHistoryError("");
    if (select) setActiveId(select);
  }

  async function toggleHistory() {
    if (historyOpen) {
      setHistoryOpen(false);
      return;
    }
    setHistoryLoading(true);
    try {
      await loadConversations();
      setHistoryOpen(true);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not load recent chats");
      setHistoryOpen(true);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function clearHistory() {
    if (!projectId || !conversations.length) return;
    setClearBusy(true);
    setHistoryError("");
    try {
      await api(`/api/projects/${projectId}/conversations`, { method: "DELETE" });
      setConversations([]);
      setMessages([]);
      setActiveId(null);
      setHistoryQuery("");
      setHistoryOpen(false);
      setClearConfirmOpen(false);
      clearRuntime(projectId);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not clear recent chats");
    } finally {
      setClearBusy(false);
    }
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
    stopAction();
    setBusy(false);
    setRunning(false);
    const conv = await api<Conversation>(`/api/projects/${projectId}/conversations`, {
      method: "POST",
    });
    setActiveId(conv.id);
    setMessages([]);
    setProposal(null);
    setActionRequest("");
    setActiveSkillRun(false);
    setCmdOutput("");
    setCmdSummary("");
    setTerminalOpen(false);
    clearRuntime(projectId);
    setHistoryOpen(false);
    await loadConversations(conv.id);
  }

  useEffect(() => {
    const runtime = readRuntime(projectId);
    if (runtime) {
      setActiveId(runtime.activeId);
      setMessages(runtime.messages);
      setProposal(runtime.proposal);
      setActionRequest(runtime.actionRequest);
      setCmdOutput(runtime.cmdOutput);
      setCmdSummary(runtime.cmdSummary);
      setActivity("");
      setBusy(false);
      setRunning(false);
      setTerminalOpen(false);
    } else {
      setMessages([]);
      setActiveId(null);
      setProposal(null);
      setActionRequest("");
      setCmdOutput("");
      setCmdSummary("");
      setActivity("");
      setBusy(false);
      setRunning(false);
      setTerminalOpen(false);
    }
    loadConversations().catch(console.error);
    setTerminalOpen(false);
    setHistoryOpen(false);
    setHistoryQuery("");
    setSkills([]);
    setCommands([]);
    if (projectId) {
      api<Skill[]>(`/api/projects/${projectId}/skills`).then(setSkills).catch(console.error);
      api<AllowCommand[]>(`/api/projects/${projectId}/commands`).then(setCommands).catch(console.error);
    }
  }, [projectId]);

  useEffect(() => {
    writeRuntime(projectId, {
      activeId,
      messages,
      proposal,
      actionRequest,
      cmdOutput,
      cmdSummary,
      activity,
      busy,
      running,
    });
  }, [projectId, activeId, messages, proposal, actionRequest, cmdOutput, cmdSummary, activity, busy, running]);

  useEffect(() => {
    const skillId = searchParams.get("skill");
    if (!projectId || !skillId) return;
    api<Skill>(`/api/projects/${projectId}/skills/${skillId}`)
      .then((skill) => {
        if (!skill.compiled || !skill.tested) return;
        setInput(`/${skillSlug(skill.name)} `);
        setMode("support");
        setActiveSkillRun(true);
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
  const command = mode === "support" ? commandQuery(input) : null;
  const slashMatches = useMemo(() => {
    if (slash === null) return [];
    return skills.filter((s) => {
      const hay = `${s.name} ${skillSlug(s.name)} ${s.goal || ""}`.toLowerCase();
      return slash === "" || hay.includes(slash) || skillSlug(s.name).startsWith(slash);
    });
  }, [skills, slash]);

  const commandMatches = useMemo(() => {
    if (command === null) return [];
    return commands.filter((c) => {
      const hay = `${c.name} ${skillSlug(c.name)} ${c.description}`.toLowerCase();
      return command === "" || hay.includes(command) || skillSlug(c.name).startsWith(command);
    });
  }, [commands, command]);

  useEffect(() => {
    setSlashIndex(0);
    setCommandIndex(0);
  }, [slash, command]);

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

  function applyCommand(commandItem: AllowCommand) {
    setInput(`@${skillSlug(commandItem.name)} `);
    setCommandIndex(0);
  }

  async function send(e?: FormEvent, preset?: string) {
    e?.preventDefault();
    const text = (preset ?? input).trim();
    if (!projectId || !text || busy) return;
    if (mode === "support" && text.startsWith("/")) setActiveSkillRun(true);
    setInput("");
    if (mode === "support" && text.startsWith("@")) {
      const token = text.slice(1).trim().toLowerCase();
      const selected = commands.find(
        (item) => skillSlug(item.name) === token || item.name.toLowerCase() === token
      );
      if (selected) {
        setMessages((m) => [
          ...m,
          { role: "user", content: text },
          {
            role: "assistant",
            content: `Ready to run ${selected.name}. Confirm the action below.`,
          },
        ]);
        setProposal({
          id: selected.id,
          name: selected.name,
          description: selected.description,
          command: selected.command,
          cwd: selected.cwd,
          reason: "Selected from the approved command list.",
        });
        setActionRequest(text);
        setTerminalOpen(false);
        return;
      }
    }
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setBusy(true);
    setActivity("thinking");
    const controller = new AbortController();
    actionController.current = controller;
    try {
      const res = await fetch(`/api/projects/${projectId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: activeId, message: text, mode }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await res.text());
      await readSse(res, (event) => {
        if (event.type === "conversation" && typeof event.id === "string") {
          setActiveId(event.id);
        }
        if (event.type === "token" && typeof event.text === "string") {
          setActivity("writing response");
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
          const next = event.command as CommandProposal;
          setActivity("preparing action");
          setActionRequest("");
          setProposal(next);
          showAssistant(`Ready to run ${next.name}. Confirm the action below.`, true);
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
      showAssistant("I could not produce a reply for that request. Try sending it again.", true);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        showAssistant(error instanceof Error ? error.message : "The request failed before a reply was returned.");
      }
    } finally {
      if (actionController.current === controller) actionController.current = null;
      setBusy(false);
      setActivity("");
    }
  }

  async function continueSkill() {
    if (!projectId || !activeId || !activeSkillRun || busy) return;
    const text = "Continue the active tested skill from the next step. Use the last command result to decide whether to proceed or skip optional steps. Do not ask me for a response unless an explicit command confirmation is required.";
    setBusy(true);
    setActivity("continuing skill");
    const controller = new AbortController();
    actionController.current = controller;
    setMessages((current) => [...current, { role: "assistant", content: "" }]);
    let responseText = "";
    try {
      const res = await fetch(`/api/projects/${projectId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: activeId, message: text, mode: "support" }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await res.text());
      await readSse(res, (event) => {
        if (event.type === "command_proposal" && event.command) {
          const next = event.command as CommandProposal;
          setActivity("preparing next action");
          setProposal(next);
          setTerminalOpen(false);
          if (!responseText.trim()) {
            responseText = `Ready to run ${next.name}. Confirm the action below.`;
            setMessages((current) => {
              const copy = [...current];
              const last = copy[copy.length - 1];
              if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: responseText };
              return copy;
            });
          }
        }
        if (event.type === "token" && typeof event.text === "string") {
          setActivity("writing response");
          responseText += event.text;
          setMessages((current) => {
            const copy = [...current];
            const last = copy[copy.length - 1];
            if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: responseText };
            return copy;
          });
        }
      });
      await loadConversations();
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
    } finally {
      if (actionController.current === controller) actionController.current = null;
      setBusy(false);
      setActivity("");
    }
  }

  async function confirmRun() {
    if (!projectId || !proposal) return;
    setRunning(true);
    setActivity("running command");
    setCmdOutput("");
    setCmdSummary("");
    setTerminalOpen(true);
    const controller = new AbortController();
    actionController.current = controller;
    let succeeded = false;
    try {
      const res = await fetch(`/api/projects/${projectId}/commands/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command_id: proposal.id,
          conversation_id: activeId,
          request_text: actionRequest || undefined,
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await res.text());
      await readSse(res, (event) => {
        if (event.type === "output" && typeof event.text === "string") {
          setCmdOutput((s) => s + event.text);
        }
        if (event.type === "status" && typeof event.text === "string") {
          setCmdOutput((s) => `${s}${event.text}\n`);
        }
        if (event.type === "exit" && typeof event.code === "number") {
          setCmdOutput((s) => `${s}Process exited with code ${event.code}.\n`);
        }
        if (event.type === "summary" && typeof event.text === "string") {
          setActivity("summarizing result");
          setCmdSummary(event.text);
          showAssistant(event.text);
        }
        if (event.type === "error" && typeof event.text === "string") {
          setCmdOutput((s) => s + event.text);
          showAssistant(event.text);
        }
      });
      succeeded = true;
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        showAssistant(error instanceof Error ? error.message : "The command failed before it returned a result.");
      }
    } finally {
      if (actionController.current === controller) actionController.current = null;
      setRunning(false);
      setActivity("");
      if (succeeded) {
        setProposal(null);
        setCmdOutput("");
        setCmdSummary("");
        setTerminalOpen(false);
        setActionRequest("");
        if (activeId) await openConversation(activeId);
        if (activeSkillRun && !controller.signal.aborted) await continueSkill();
      }
    }
  }

  async function approveDraft() {
    if (!projectId || !proposal?.draft) return;
    const command = await api<AllowCommand>(`/api/projects/${projectId}/commands`, {
      method: "POST",
      body: JSON.stringify({
        name: proposal.name,
        description: proposal.description,
        cwd: proposal.cwd,
        command: proposal.command,
      }),
    });
    setProposal({ ...proposal, id: command.id, draft: false });
  }

  async function runDraftOnce() {
    if (!projectId || !proposal?.draft) return;
    setRunning(true);
    setActivity("running command");
    setCmdOutput("");
    setCmdSummary("");
    setTerminalOpen(false);
    const controller = new AbortController();
    actionController.current = controller;
    try {
      const res = await fetch(`/api/projects/${projectId}/commands/run-once`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: proposal.name,
          description: proposal.description,
          command: proposal.command,
          cwd: proposal.cwd,
          conversation_id: activeId,
          request_text: actionRequest || undefined,
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await res.text());
      await readSse(res, (event) => {
        if (event.type === "output" && typeof event.text === "string") {
          setCmdOutput((s) => s + event.text);
        }
        if (event.type === "status" && typeof event.text === "string") {
          setCmdOutput((s) => `${s}${event.text}\n`);
        }
        if (event.type === "exit" && typeof event.code === "number") {
          setCmdOutput((s) => `${s}Process exited with code ${event.code}.\n`);
        }
        if (event.type === "summary" && typeof event.text === "string") {
          setActivity("summarizing result");
          setCmdSummary(event.text);
        }
        if (event.type === "error" && typeof event.text === "string") {
          setCmdOutput((s) => s + event.text);
        }
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) throw error;
    } finally {
      if (actionController.current === controller) actionController.current = null;
      setRunning(false);
      setActivity("");
      setProposal(null);
      setCmdOutput("");
      setCmdSummary("");
      setTerminalOpen(false);
      setActionRequest("");
      if (activeId) await openConversation(activeId);
      if (activeSkillRun && !controller.signal.aborted) await continueSkill();
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
              onClick={toggleHistory}
            >
              {historyLoading ? "Loading..." : "Recents"}
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
                <div className="history-actions">
                  <button type="button" className="subtle" onClick={() => setClearConfirmOpen(true)} disabled={!conversations.length}>
                    Clear
                  </button>
                </div>
                {clearConfirmOpen && (
                  <div className="history-confirm">
                    <span>Clear all chats?</span>
                    <button type="button" className="subtle" onClick={() => setClearConfirmOpen(false)} disabled={clearBusy}>Cancel</button>
                    <button type="button" className="danger" onClick={clearHistory} disabled={clearBusy}>{clearBusy ? "Clearing…" : "Clear"}</button>
                  </div>
                )}
                <div className="history-scroll">
                  {historyError && <p className="muted history-error">{historyError}</p>}
                  {historyGroups.length === 0 && (
                    <p className="muted" style={{ padding: "8px 10px", margin: 0 }}>
                      {historyError
                        ? "Recent chats could not be loaded"
                        : conversations.length === 0
                          ? "No chats yet"
                          : "No matching chats"}
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
            <p className="empty-prompt">How can I help with this app?</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`msg ${m.role}`} key={i}>
            {m.role === "user" ? (
              <div className="bubble">{m.content}</div>
            ) : (
              <div className="markdown">
                {m.content ? (
                  <Markdown components={{ code: MarkdownCode }}>{m.content}</Markdown>
                ) : busy && i === messages.length - 1 ? (
                  <span className="activity-label">{activity}</span>
                ) : null}
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
        {command !== null && (
          <div className="slash-menu command-menu">
            <div className="slash-menu-label">Approved commands</div>
            {commandMatches.length === 0 ? (
              <p className="muted" style={{ margin: 0, padding: "6px 10px" }}>
                {commands.length === 0 ? "No approved commands yet" : "No matching command"}
              </p>
            ) : (
              commandMatches.map((item, i) => (
                <button
                  type="button"
                  key={item.id}
                  className={i === commandIndex ? "active" : ""}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    applyCommand(item);
                  }}
                >
                  <strong>@{skillSlug(item.name)}</strong>
                  <span>{item.description || item.command}</span>
                </button>
              ))
            )}
          </div>
        )}
        <div className={`composer-box ${busy || running || input.trim() ? "processing" : ""}`}>
          <textarea
            placeholder={
              mode === "support" ? "Message AppSense…  Type / for skills or @ for commands" : "Message AppSense…"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (command !== null && commandMatches.length > 0) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setCommandIndex((i) => (i + 1) % commandMatches.length);
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setCommandIndex((i) => (i - 1 + commandMatches.length) % commandMatches.length);
                  return;
                }
                if (e.key === "Tab") {
                  e.preventDefault();
                  applyCommand(commandMatches[commandIndex]);
                  return;
                }
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(undefined, `@${skillSlug(commandMatches[commandIndex].name)}`);
                  return;
                }
              }
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
                if (e.key === "Tab") {
                  e.preventDefault();
                  applySkill(slashMatches[slashIndex]);
                  return;
                }
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(undefined, `/${skillSlug(slashMatches[slashIndex].name)}`);
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
          {busy ? (
            <button
              type="button"
              className="stop-action"
              onClick={stopAction}
              aria-label="Stop response"
              title="Stop response"
            >
              <span aria-hidden />
            </button>
          ) : (
            <button className="primary" disabled={!input.trim()}>
              Send
            </button>
          )}
        </div>
      </form>
      {proposal && (
        <section className="support-action" aria-label="Support action">
          <div className="support-action-head">
            <div>
              <span className="support-action-kicker">{running ? "Running terminal" : "Action proposed"}</span>
              <h3>{proposal.name}</h3>
            </div>
            <button className="subtle" onClick={() => { setProposal(null); setActionRequest(""); }} disabled={running}>
              Dismiss
            </button>
          </div>
          {proposal.reason && <p className="muted">{proposal.reason}</p>}
          {proposal.description && <p>{proposal.description}</p>}
          <div className="support-command-meta">Working directory: {proposal.cwd}</div>
          <pre className="support-command">{proposal.command}</pre>
          <div className="support-action-controls">
            <button
              type="button"
              className="terminal-toggle"
              onClick={() => setTerminalOpen((open) => !open)}
              aria-expanded={terminalOpen}
            >
              <span className={`terminal-dot ${running ? "live" : ""}`} />
              Terminal {running ? "running" : "output"}
              <span aria-hidden>{terminalOpen ? "⌃" : "⌄"}</span>
            </button>
            {running ? (
              <button
                type="button"
                className="stop-action"
                onClick={stopAction}
                aria-label="Stop command"
                title="Stop command"
              >
                <span aria-hidden />
              </button>
            ) : proposal.draft ? (
              <>
                <button className="subtle" onClick={approveDraft}>Save for future</button>
                <button className="primary" onClick={runDraftOnce}>Approve & run once</button>
              </>
            ) : (
              <button className="primary" onClick={confirmRun}>Confirm run</button>
            )}
          </div>
          {terminalOpen && (
            <pre className="terminal-output">{cmdOutput || "Waiting for command output..."}</pre>
          )}
          {cmdSummary && <p className="command-summary">{cmdSummary}</p>}
        </section>
      )}
    </div>
  );
}
