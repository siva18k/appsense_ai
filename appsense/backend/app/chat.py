from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

import httpx

from . import commands as command_mod
from . import db as database
from .logs import tail_logs
from .rag import code_collection, kb_collection, query_project, skills_collection
from .settings import get_settings
from .skills import list_skills

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search the project's uploaded knowledge base (PDFs and notes).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search indexed source code for this project.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a source file from a linked repository. Path must be inside a linked repo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or repo-relative path"},
                    "repo_id": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tail_logs",
            "description": "Read the last lines of a configured application log file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "lines": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_command",
            "description": "Select a matching allowlisted command, or draft a safe command for the user to review and explicitly add to the allowlist. Never execute a drafted command directly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_id": {
                        "type": "string",
                        "description": "Allowlisted command name or id",
                    },
                    "reason": {"type": "string"},
                    "draft_name": {"type": "string"},
                    "draft_description": {"type": "string"},
                    "draft_command": {"type": "string"},
                    "draft_cwd": {"type": "string"},
                },
                "required": ["name_or_id"],
            },
        },
    },
]

TOOLS_CHAT = [t for t in TOOLS if t["function"]["name"] != "propose_command"]


def _linked_repos(project_id: str) -> list[dict]:
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM repos WHERE project_id = ?", (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def _read_sandboxed_file(project_id: str, path: str, repo_id: str | None) -> dict:
    repos = _linked_repos(project_id)
    if repo_id:
        repos = [r for r in repos if r["id"] == repo_id]
    if not repos:
        return {"ok": False, "error": "No matching linked repository."}
    requested = Path(path).expanduser()
    for repo in repos:
        root = Path(repo["local_path"]).resolve()
        candidate = requested if requested.is_absolute() else (root / path)
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved.is_relative_to(root):
            text = resolved.read_text(encoding="utf-8", errors="replace")
            if len(text) > 40_000:
                text = text[:40_000] + "\n...[truncated]"
            return {
                "ok": True,
                "path": str(resolved.relative_to(root)),
                "repo": repo["name"],
                "text": text,
            }
    return {"ok": False, "error": "File is outside linked repositories or does not exist."}


def _format_hits(hits: list[dict], kind: str) -> str:
    if not hits:
        return f"No {kind} matches."
    parts = []
    for h in hits:
        meta = h.get("metadata") or {}
        label = meta.get("title") or meta.get("path") or kind
        parts.append(f"[{label}]\n{h.get('text', '')}")
    return "\n\n---\n\n".join(parts)


def _skill_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def expand_skill_slash(skills: list[dict], user_text: str) -> str:
    text = (user_text or "").strip()
    if not text.startswith("/"):
        return user_text
    token, _, extra = text[1:].partition(" ")
    token = token.lower()
    if not token:
        return user_text
    for skill in skills:
        name = skill.get("name") or ""
        if _skill_slug(name) != token and name.lower() != token:
            continue
        playbook = (
            "Follow this skill playbook and complete it step by step.\n\n"
            f"# {name}\n\n{skill.get('body') or skill.get('goal') or ''}"
        )
        extra = extra.strip()
        if extra:
            return f"{playbook}\n\nAdditional request from the user:\n{extra}"
        return playbook
    return user_text


def _looks_operational(text: str) -> bool:
    return bool(
        re.search(
            r"\b(restart|start|stop|run|execute|launch|shutdown|kill|reload|" \
            r"deploy|rollback|health[- ]check|check)\b",
            text or "",
            re.IGNORECASE,
        )
    )


def _runtime_environment(default_command_cwd: str) -> str:
    shell = os.getenv("SHELL") or "unknown shell"
    node = shutil.which("node") or "not available"
    npm = shutil.which("npm") or "not available"
    return "\n".join(
        [
            f"- OS: {platform.system()} {platform.release()} ({platform.machine()})",
            f"- Shell: {shell}",
            f"- Python: {sys.executable} ({platform.python_version()})",
            f"- Node: {node}",
            f"- npm: {npm}",
            f"- Default working directory: {default_command_cwd or 'not configured'}",
        ]
    )


def retrieve_context(project_id: str, query: str) -> list[dict]:
    kb = query_project(kb_collection(), project_id, query, n_results=8)
    code = query_project(code_collection(), project_id, query, n_results=5)
    skills = query_project(skills_collection(), project_id, query, n_results=4)
    citations = []
    for h in kb:
        meta = h.get("metadata") or {}
        citations.append(
            {
                "kind": "knowledge",
                "title": meta.get("title"),
                "text": (h.get("text") or "")[:400],
            }
        )
    for h in skills:
        meta = h.get("metadata") or {}
        citations.append(
            {
                "kind": "skill",
                "title": meta.get("title"),
                "text": (h.get("text") or "")[:500],
            }
        )
    for h in code:
        meta = h.get("metadata") or {}
        citations.append(
            {
                "kind": "code",
                "title": meta.get("path"),
                "text": (h.get("text") or "")[:400],
            }
        )
    return citations


def _system_prompt(
    project: dict,
    allowlist: list[dict],
    log_paths: list[dict],
    skills: list[dict],
    mode: str,
    default_command_cwd: str = "",
    target_app_python: str = "",
    target_app_env_file: str = "",
) -> str:
    cmds = "\n".join(
        f"- {c['name']} (id={c['id']}): {c['description']} | `{c['command']}` cwd={c['cwd']}"
        for c in allowlist
    ) or "(none configured)"
    logs = "\n".join(f"- {l['label']}: {l['path']}" for l in log_paths) or "(none configured)"
    skill_list = "\n".join(
        f"- {s['name']}: {(s.get('goal') or '')[:160]}" for s in skills
    ) or "(none)"
    if mode == "support":
        mode_block = """You are in **Support mode**.
Answer using retrieved code learning, knowledge, skills/playbooks, and source snippets.
For operational actions (restart a service, run a batch job), you MUST call propose_command. Do not answer with shell instructions, numbered manual steps, or commands in a code block. Prefer a matching allowlisted command. If none matches, draft a command with draft_name, draft_description, draft_command, and draft_cwd for the user to review and add to the allowlist. Never execute a draft without explicit user approval.
You are already in Support mode. Never tell the user to switch to Support mode, even if an earlier message in the conversation suggested that. Act on the current request through the proposal and confirmation flow.
If the user invokes a skill with /skill-name, follow that playbook step by step. Still confirm allowlisted commands before execution."""
    else:
        mode_block = """You are in **Chat mode**.
Answer with information only. Explain how the application works, what a log means, and what someone *could* do — but do not propose, request, or trigger any operational command.
Do not call propose_command. Do not walk through executing allowlisted actions. If the user wants something done on the system, tell them to switch to Support mode."""
    return f"""You are AppSense, an IT application support assistant for the project "{project['name']}".
{project.get('description') or ''}

{mode_block}
If you are unsure, say so.
When explaining how to run something, mention the relevant article or file path in the prose if it helps. Do not append a sources list, knowledge chunks, citations, or retrieved-snippet dump at the bottom of the answer.
If the user asks for an overview of the app, use the scanned code-learning document first.

Configured skills:
{skill_list}

Allowlisted commands:
{cmds}

Default command working directory:
{default_command_cwd or "(not configured; ask the user before drafting a command)"}

Runtime environment available for command planning:
{_runtime_environment(default_command_cwd)}
Target application Python:
{target_app_python or "not configured"}
Target application environment file:
{target_app_env_file or "not configured"}

Configured logs:
{logs}

Retrieved context will be provided with the user question. Use tools if you need more detail, logs, or a specific file.
"""


def run_tool(project_id: str, name: str, arguments: dict, mode: str = "chat") -> tuple[str, dict | None]:
    if name == "search_knowledge":
        hits = query_project(kb_collection(), project_id, arguments.get("query", ""), n_results=6)
        return _format_hits(hits, "knowledge"), None
    if name == "search_code":
        hits = query_project(code_collection(), project_id, arguments.get("query", ""), n_results=6)
        return _format_hits(hits, "code"), None
    if name == "read_file":
        result = _read_sandboxed_file(
            project_id, arguments.get("path", ""), arguments.get("repo_id")
        )
        return json.dumps(result), None
    if name == "tail_logs":
        result = tail_logs(
            project_id,
            arguments.get("path"),
            int(arguments.get("lines") or 120),
        )
        return json.dumps(result), None
    if name == "propose_command":
        if mode != "support":
            return json.dumps(
                {"ok": False, "error": "Actions are only available in Support mode."}
            ), None
        cmd = command_mod.match_command(project_id, arguments.get("name_or_id", ""))
        if not cmd:
            draft_command = (arguments.get("draft_command") or "").strip()
            draft_cwd = (arguments.get("draft_cwd") or "").strip()
            if draft_command and draft_cwd:
                proposal = {
                    "id": "",
                    "name": (arguments.get("draft_name") or arguments.get("name_or_id") or "Suggested command").strip(),
                    "description": (arguments.get("draft_description") or "").strip(),
                    "command": draft_command,
                    "cwd": draft_cwd,
                    "reason": "This command is dynamically generated and not from allow list.",
                    "draft": True,
                }
                return json.dumps({"ok": True, "draft": proposal}), proposal
            available = [c["name"] for c in command_mod.list_commands(project_id)]
            return json.dumps(
                {
                    "ok": False,
                    "error": "Command is not allowlisted.",
                    "available": available,
                }
            ), None
        proposal = {
            "id": cmd["id"],
            "name": cmd["name"],
            "description": cmd["description"],
            "command": cmd["command"],
            "cwd": cmd["cwd"],
            "reason": arguments.get("reason") or "",
        }
        return json.dumps({"ok": True, "proposal": proposal}), proposal
    return json.dumps({"error": f"Unknown tool {name}"}), None


async def stream_chat(project: dict, conversation_id: str, user_text: str, mode: str = "chat"):
    settings = get_settings()
    if not settings.llm_api_key:
        yield {"type": "error", "text": "LLM_API_KEY is not set. Add it in Settings / .env."}
        return
    support = (mode or "chat").lower() == "support"
    allowlist = command_mod.list_commands(project["id"])
    default_command_cwd = str(settings.default_command_cwd)
    target_app_root = str(settings.target_app_root)
    action_enabled = support
    operational_request = action_enabled and _looks_operational(user_text)
    skills = list_skills(project["id"], executable_only=True)
    llm_text = expand_skill_slash(skills, user_text) if support else user_text
    citations = retrieve_context(project["id"], llm_text)
    with database.db() as conn:
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM log_paths WHERE project_id = ?", (project["id"],)
            ).fetchall()
        ]
        history = [
            dict(r)
            for r in conn.execute(
                """SELECT role, content FROM messages
                   WHERE conversation_id = ? ORDER BY created_at ASC""",
                (conversation_id,),
            ).fetchall()
        ]
        if history and history[-1]["role"] == "user" and history[-1]["content"] == user_text:
            history = history[:-1]

    context_block = "\n\n".join(
        f"- ({c['kind']}) {c['title']}: {c['text']}" for c in citations
    ) or "(no retrieved snippets yet)"

    messages = [
        {"role": "system", "content": _system_prompt(project, allowlist, logs, skills, "support" if action_enabled else "chat", target_app_root, settings.target_app_python, str(settings.target_app_env_file or ""))},
        *[
            {
                "role": m["role"],
                "content": (
                    expand_skill_slash(skills, m["content"])
                    if support and m["role"] == "user"
                    else m["content"]
                ),
            }
            for m in history
            if m["role"] in ("user", "assistant")
        ],
        {
            "role": "user",
            "content": f"{llm_text}\n\n---\nRetrieved context:\n{context_block}",
        },
    ]

    url = f"{settings.llm_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    assistant_parts: list[str] = []
    proposal = None

    async with httpx.AsyncClient(timeout=120.0) as client:
        for _round in range(4):
            payload = {
                "model": settings.llm_model,
                "messages": messages,
                "tools": TOOLS if action_enabled else TOOLS_CHAT,
                "stream": True,
                "temperature": 0.2,
            }
            if operational_request:
                payload["tools"] = [TOOLS[-1]]
                payload["tool_choice"] = "required"
            tool_calls: dict[int, dict] = {}
            finish_reason = None
            assistant_parts = []
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    yield {
                        "type": "error",
                        "text": f"LLM error {resp.status_code}: {body.decode('utf-8', errors='replace')[:800]}",
                    }
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        assistant_parts.append(delta["content"])
                        yield {"type": "token", "text": delta["content"]}
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        slot = tool_calls.setdefault(
                            idx,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] += fn["name"]
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]

            if tool_calls and finish_reason == "tool_calls":
                assistant_msg = {
                    "role": "assistant",
                    "content": "".join(assistant_parts) or "Checking the requested status.",
                    "tool_calls": [
                        {
                            "id": slot["id"] or f"call_{idx}",
                            "type": "function",
                            "function": {
                                "name": slot["name"],
                                "arguments": slot["arguments"] or "{}",
                            },
                        }
                        for idx, slot in sorted(tool_calls.items())
                    ],
                }
                messages.append(assistant_msg)
                for idx, slot in sorted(tool_calls.items()):
                    try:
                        args = json.loads(slot["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield {
                        "type": "tool",
                        "name": slot["name"],
                        "arguments": args,
                    }
                    result, maybe_proposal = run_tool(project["id"], slot["name"], args, "support" if support else "chat")
                    if maybe_proposal:
                        proposal = maybe_proposal
                        yield {"type": "command_proposal", "command": maybe_proposal}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": slot["id"] or f"call_{idx}",
                            "content": result,
                        }
                    )
                continue
            break

    final = "".join(assistant_parts).strip()
    extra = json.dumps({"proposal": proposal}) if proposal else None
    with database.db() as conn:
        conn.execute(
            """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
               VALUES (?, ?, 'assistant', ?, ?, ?)""",
            (database.new_id(), conversation_id, final, extra, database.now_iso()),
        )
    yield {"type": "done", "content": final}


async def summarize_command_output(project: dict, command: dict, output: str, exit_code: int | None) -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        return "Command finished. Add an LLM API key in Settings to generate a summary."
    status = "completed successfully" if exit_code == 0 else f"exited with code {exit_code}"
    excerpt = output[-12000:] if output else "(no output)"
    prompt = f"""Summarize this supported-application command execution for a non-technical user.
State whether it {status} and the key result in 1-2 short sentences.
Do not invent facts. Maximum 280 characters, no markdown heading, no code block.

Command: {command.get('command', '')}
Working directory: {command.get('cwd', '')}
Output:
{excerpt}"""
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": "You summarize command results accurately and briefly."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "stream": False,
                },
            )
            if response.status_code >= 400:
                return f"Command {status}. Summary unavailable (LLM returned HTTP {response.status_code})."
            data = response.json()
            summary = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
            if len(summary) > 280:
                summary = f"{summary[:277].rstrip()}..."
            return summary or f"Command {status}."
    except Exception as exc:
        return f"Command {status}. Summary unavailable: {exc}"[:500]
