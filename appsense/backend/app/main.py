from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import commands as command_mod
from . import db as database
from .chat import stream_chat, summarize_command_output
from .ingest_code import add_local_repo, add_remote_repo, delete_repo_vectors, index_repo
from .ingest_kb import (
    create_pdf_doc,
    create_text_doc,
    create_upload_doc,
    delete_kb_vectors,
    make_summary,
    reindex_project_kb,
    replace_upload_doc,
    update_text_doc,
)
from .scan_code import scan_repository
from .skills import (
    delete_skill,
    delete_skill_vectors,
    get_skill,
    list_skills,
    refine_skill,
    reindex_project_skills,
    save_skill,
    test_skill,
)
from .paths import ensure_data_dirs
from .settings import get_settings, public_settings_dict, update_env

app = FastAPI(title="AppSense")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_data_dirs()
    database.init_db()


class ProjectIn(BaseModel):
    name: str
    description: str = ""


class TextDocIn(BaseModel):
    title: str
    body: str


class RepoLocalIn(BaseModel):
    name: str = ""
    path: str


class RepoRemoteIn(BaseModel):
    name: str = ""
    url: str


class CommandIn(BaseModel):
    name: str
    description: str = ""
    cwd: str = ""
    command: str


class LogPathIn(BaseModel):
    label: str
    path: str


class SkillIn(BaseModel):
    name: str
    goal: str
    body: str = ""
    refined: bool = False


class SkillRefineIn(BaseModel):
    name: str = ""
    goal: str


class SettingsIn(BaseModel):
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    embedding_model: str | None = None
    chroma_path: str | None = None
    sqlite_path: str | None = None
    default_command_cwd: str | None = None
    default_command_python: str | None = None
    target_app_root: str | None = None
    target_app_python: str | None = None
    target_app_env_file: str | None = None


class ChatIn(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1)
    mode: str = "chat"


class RunCommandIn(BaseModel):
    command_id: str
    conversation_id: str | None = None
    request_text: str | None = None


class RunDraftCommandIn(BaseModel):
    name: str
    description: str = ""
    command: str
    cwd: str
    conversation_id: str | None = None
    request_text: str | None = None


def _project(project_id: str) -> dict[str, Any]:
    with database.db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


def _conversation_title(message: str) -> str:
    title = " ".join(message.split()).strip()
    if len(title) > 60:
        return f"{title[:57].rstrip()}..."
    return title or "New chat"


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/settings")
def get_public_settings():
    return public_settings_dict()


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    mapping = {
        "llm_base_url": "LLM_BASE_URL",
        "llm_model": "LLM_MODEL",
        "llm_api_key": "LLM_API_KEY",
        "embedding_model": "EMBEDDING_MODEL",
        "chroma_path": "CHROMA_PATH",
        "sqlite_path": "SQLITE_PATH",
        "default_command_cwd": "DEFAULT_COMMAND_CWD",
        "default_command_python": "DEFAULT_COMMAND_PYTHON",
        "target_app_root": "TARGET_APP_ROOT",
        "target_app_python": "TARGET_APP_PYTHON",
        "target_app_env_file": "TARGET_APP_ENV_FILE",
    }
    updates = {}
    for field, env_key in mapping.items():
        value = getattr(body, field)
        if value is not None:
            updates[env_key] = value
    return update_env(updates)


@app.get("/api/projects")
def list_projects():
    with database.db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at ASC").fetchall()
    return database.rows_to_list(rows)


@app.post("/api/projects")
def create_project(body: ProjectIn):
    pid = database.new_id()
    created = database.now_iso()
    with database.db() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (pid, body.name.strip(), body.description.strip(), created),
        )
    return _project(pid)


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, body: ProjectIn):
    _project(project_id)
    with database.db() as conn:
        conn.execute(
            "UPDATE projects SET name = ?, description = ? WHERE id = ?",
            (body.name.strip(), body.description.strip(), project_id),
        )
    return _project(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    _project(project_id)
    with database.db() as conn:
        docs = conn.execute("SELECT id FROM kb_docs WHERE project_id = ?", (project_id,)).fetchall()
        repos = conn.execute("SELECT id FROM repos WHERE project_id = ?", (project_id,)).fetchall()
        skill_rows = conn.execute("SELECT id FROM skills WHERE project_id = ?", (project_id,)).fetchall()
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    for d in docs:
        delete_kb_vectors(d["id"])
    for r in repos:
        delete_repo_vectors(r["id"])
    for s in skill_rows:
        delete_skill_vectors(s["id"])
    settings = get_settings()
    for folder in (settings.repos_path / project_id, settings.uploads_path / project_id):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True}


@app.get("/api/projects/{project_id}/conversations")
def list_conversations(project_id: str):
    _project(project_id)
    with database.db() as conn:
        rows = conn.execute(
                        """SELECT c.* FROM conversations c
                             WHERE c.project_id = ?
                                 AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
                             ORDER BY c.created_at DESC""",
            (project_id,),
        ).fetchall()
        conversations = database.rows_to_list(rows)
        for conversation in conversations:
            if conversation["title"] != "New chat":
                continue
            message = conn.execute(
                """SELECT content FROM messages
                   WHERE conversation_id = ? AND role = 'user'
                   ORDER BY created_at ASC LIMIT 1""",
                (conversation["id"],),
            ).fetchone()
            if message:
                conversation["title"] = _conversation_title(message["content"])
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (conversation["title"], conversation["id"]),
                )
    return conversations


@app.post("/api/projects/{project_id}/conversations")
def create_conversation(project_id: str):
    _project(project_id)
    cid = database.new_id()
    created = database.now_iso()
    with database.db() as conn:
        conn.execute(
            "INSERT INTO conversations (id, project_id, title, created_at) VALUES (?, ?, ?, ?)",
            (cid, project_id, "New chat", created),
        )
    return {"id": cid, "project_id": project_id, "title": "New chat", "created_at": created}


@app.get("/api/projects/{project_id}/conversations/{conversation_id}")
def get_conversation(project_id: str, conversation_id: str):
    _project(project_id)
    with database.db() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND project_id = ?",
            (conversation_id, project_id),
        ).fetchone()
        if not conv:
            raise HTTPException(404, "Conversation not found")
        msgs = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
    return {"conversation": dict(conv), "messages": database.rows_to_list(msgs)}


@app.post("/api/projects/{project_id}/chat")
async def chat(project_id: str, body: ChatIn):
    project = _project(project_id)
    conversation_id = body.conversation_id
    if not conversation_id:
        conversation_id = database.new_id()
        with database.db() as conn:
            conn.execute(
                "INSERT INTO conversations (id, project_id, title, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, project_id, "New chat", database.now_iso()),
            )
    else:
        with database.db() as conn:
            conv = conn.execute(
                "SELECT id FROM conversations WHERE id = ? AND project_id = ?",
                (conversation_id, project_id),
            ).fetchone()
        if not conv:
            raise HTTPException(404, "Conversation not found")

    with database.db() as conn:
        conn.execute(
            """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
               VALUES (?, ?, 'user', ?, NULL, ?)""",
            (database.new_id(), conversation_id, body.message, database.now_iso()),
        )
        conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND title = 'New chat'",
            (_conversation_title(body.message), conversation_id),
        )

    async def events():
        yield _sse({"type": "conversation", "id": conversation_id})
        async for event in stream_chat(project, conversation_id, body.message, body.mode):
            yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/api/projects/{project_id}/knowledge")
def list_knowledge(project_id: str, q: str | None = None, kind: str = "all"):
    _project(project_id)
    extra = ""
    params: list = [project_id]
    if kind == "uploads":
        extra = " AND source_type != 'code_scan'"
    with database.db() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute(
                f"""SELECT id, project_id, title, source_type, filename, created_at, updated_at, summary,
                          substr(body, 1, 400) AS excerpt, length(body) AS body_len
                   FROM kb_docs WHERE project_id = ?{extra} AND (title LIKE ? OR body LIKE ?)
                   ORDER BY COALESCE(updated_at, created_at) DESC""",
                (*params, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT id, project_id, title, source_type, filename, created_at, updated_at, summary,
                          substr(body, 1, 400) AS excerpt, length(body) AS body_len
                   FROM kb_docs WHERE project_id = ?{extra}
                   ORDER BY COALESCE(updated_at, created_at) DESC""",
                params,
            ).fetchall()
    items = []
    for row in rows:
        d = dict(row)
        if not d.get("summary"):
            d["summary"] = make_summary(d.get("excerpt") or "")
        items.append(d)
    return items


@app.get("/api/projects/{project_id}/knowledge/{doc_id}")
def get_knowledge(project_id: str, doc_id: str):
    _project(project_id)
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM kb_docs WHERE id = ? AND project_id = ?",
            (doc_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return dict(row)


@app.post("/api/projects/{project_id}/knowledge/text")
def add_text_knowledge(project_id: str, body: TextDocIn):
    _project(project_id)
    return create_text_doc(project_id, body.title, body.body)


@app.post("/api/projects/{project_id}/knowledge/upload")
async def add_upload_knowledge(
    project_id: str,
    title: str = Form(""),
    file: UploadFile = File(...),
):
    _project(project_id)
    settings = get_settings()
    dest_dir = settings.uploads_path / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "upload.bin"
    dest = dest_dir / f"{database.new_id()}_{filename}"
    dest.write_bytes(await file.read())
    return create_upload_doc(project_id, title, filename, dest)


@app.patch("/api/projects/{project_id}/knowledge/{doc_id}")
def patch_knowledge(project_id: str, doc_id: str, body: TextDocIn):
    _project(project_id)
    try:
        return update_text_doc(project_id, doc_id, body.title, body.body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/projects/{project_id}/knowledge/{doc_id}/upload")
async def replace_knowledge_file(
    project_id: str,
    doc_id: str,
    title: str = Form(""),
    file: UploadFile = File(...),
):
    _project(project_id)
    settings = get_settings()
    dest_dir = settings.uploads_path / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "upload.bin"
    dest = dest_dir / f"{database.new_id()}_{filename}"
    dest.write_bytes(await file.read())
    try:
        return replace_upload_doc(project_id, doc_id, title, filename, dest)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/projects/{project_id}/knowledge/pdf")
async def add_pdf_knowledge(
    project_id: str,
    title: str = Form(""),
    file: UploadFile = File(...),
):
    _project(project_id)
    settings = get_settings()
    dest_dir = settings.uploads_path / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "upload.pdf"
    dest = dest_dir / f"{database.new_id()}_{filename}"
    dest.write_bytes(await file.read())
    return create_pdf_doc(project_id, title, filename, dest)


@app.delete("/api/projects/{project_id}/knowledge/{doc_id}")
def delete_knowledge(project_id: str, doc_id: str):
    _project(project_id)
    with database.db() as conn:
        row = conn.execute(
            "SELECT id FROM kb_docs WHERE id = ? AND project_id = ?",
            (doc_id, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        conn.execute("DELETE FROM kb_docs WHERE id = ?", (doc_id,))
    delete_kb_vectors(doc_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/knowledge/reindex")
def reindex_knowledge(project_id: str):
    _project(project_id)
    count = reindex_project_kb(project_id)
    return {"chunks": count}


@app.get("/api/projects/{project_id}/inventory")
def project_inventory(project_id: str):
    _project(project_id)
    with database.db() as conn:
        docs = conn.execute(
            """SELECT id, project_id, title, source_type, filename, created_at, updated_at, summary,
                      substr(body, 1, 400) AS excerpt
               FROM kb_docs WHERE project_id = ?
               ORDER BY COALESCE(updated_at, created_at) DESC""",
            (project_id,),
        ).fetchall()
        repos = conn.execute(
            "SELECT * FROM repos WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        commands = conn.execute(
            "SELECT * FROM command_allowlist WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
        logs = conn.execute(
            "SELECT * FROM log_paths WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    knowledge = []
    for row in docs:
        d = dict(row)
        if not d.get("summary"):
            d["summary"] = make_summary(d.get("excerpt") or "")
        knowledge.append(d)
    return {
        "knowledge": knowledge,
        "repos": database.rows_to_list(repos),
        "commands": database.rows_to_list(commands),
        "logs": database.rows_to_list(logs),
        "skills": list_skills(project_id),
    }


@app.post("/api/projects/{project_id}/rerag")
def rerag_project(project_id: str):
    _project(project_id)
    kb_chunks = reindex_project_kb(project_id)
    skill_chunks = reindex_project_skills(project_id)
    with database.db() as conn:
        repos = conn.execute("SELECT * FROM repos WHERE project_id = ?", (project_id,)).fetchall()
    code_chunks = 0
    for row in repos:
        code_chunks += index_repo(dict(row))
    return {
        "kb_chunks": kb_chunks,
        "code_chunks": code_chunks,
        "skill_chunks": skill_chunks,
        "repos": len(repos),
    }


@app.post("/api/projects/{project_id}/rescan")
def rescan_project(project_id: str):
    _project(project_id)
    with database.db() as conn:
        repos = conn.execute("SELECT * FROM repos WHERE project_id = ?", (project_id,)).fetchall()
    if not repos:
        raise HTTPException(400, "No repositories linked. Add one in Code Base first.")
    results = []
    for row in repos:
        results.append(scan_repository(dict(row)))
    return {
        "repos": len(results),
        "files_read": sum(r.get("files_read", 0) for r in results),
    }


@app.get("/api/projects/{project_id}/skills")
def get_skills(project_id: str):
    _project(project_id)
    return list_skills(project_id)


@app.post("/api/projects/{project_id}/skills/refine")
def refine_skill_endpoint(project_id: str, body: SkillRefineIn):
    _project(project_id)
    if not body.goal.strip():
        raise HTTPException(400, "Describe what the skill should do first.")
    try:
        markdown = refine_skill(project_id, body.name, body.goal)
    except Exception as exc:
        raise HTTPException(502, f"Refine failed: {exc}") from exc
    return {"markdown": markdown}


@app.post("/api/projects/{project_id}/skills")
def create_skill(project_id: str, body: SkillIn):
    _project(project_id)
    return save_skill(project_id, body.name, body.goal, body.body or body.goal, body.refined)


@app.get("/api/projects/{project_id}/skills/{skill_id}")
def read_skill(project_id: str, skill_id: str):
    _project(project_id)
    skill = get_skill(project_id, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return skill


@app.patch("/api/projects/{project_id}/skills/{skill_id}")
def patch_skill(project_id: str, skill_id: str, body: SkillIn):
    _project(project_id)
    try:
        return save_skill(
            project_id, body.name, body.goal, body.body or body.goal, body.refined, skill_id
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/projects/{project_id}/skills/{skill_id}/test")
def test_skill_endpoint(project_id: str, skill_id: str):
    _project(project_id)
    try:
        return test_skill(project_id, skill_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/api/projects/{project_id}/skills/{skill_id}")
def remove_skill(project_id: str, skill_id: str):
    _project(project_id)
    delete_skill(project_id, skill_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/repos")
def list_repos(project_id: str):
    _project(project_id)
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM repos WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return database.rows_to_list(rows)


@app.post("/api/projects/{project_id}/repos/local")
def repo_local(project_id: str, body: RepoLocalIn):
    _project(project_id)
    try:
        return add_local_repo(project_id, body.name, body.path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/projects/{project_id}/repos/remote")
def repo_remote(project_id: str, body: RepoRemoteIn):
    _project(project_id)
    try:
        return add_remote_repo(project_id, body.name, body.url)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/projects/{project_id}/repos/{repo_id}/scan")
def repo_scan(project_id: str, repo_id: str):
    _project(project_id)
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM repos WHERE id = ? AND project_id = ?",
            (repo_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Repo not found")
    try:
        return scan_repository(dict(row))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Scan failed: {exc}") from exc


@app.post("/api/projects/{project_id}/repos/{repo_id}/reindex")
def repo_reindex(project_id: str, repo_id: str):
    _project(project_id)
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM repos WHERE id = ? AND project_id = ?",
            (repo_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Repo not found")
    count = index_repo(dict(row))
    with database.db() as conn:
        updated = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
    return {"chunks": count, "repo": dict(updated)}


@app.delete("/api/projects/{project_id}/repos/{repo_id}")
def delete_repo(project_id: str, repo_id: str):
    _project(project_id)
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM repos WHERE id = ? AND project_id = ?",
            (repo_id, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Repo not found")
        conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
    rec = dict(row)
    delete_repo_vectors(repo_id)
    if rec.get("scan_doc_id"):
        with database.db() as conn:
            conn.execute(
                "DELETE FROM kb_docs WHERE id = ? AND project_id = ?",
                (rec["scan_doc_id"], project_id),
            )
        delete_kb_vectors(rec["scan_doc_id"])
    if rec["kind"] == "remote":
        shutil.rmtree(rec["local_path"], ignore_errors=True)
    return {"ok": True}


@app.get("/api/projects/{project_id}/commands")
def get_commands(project_id: str):
    _project(project_id)
    return command_mod.list_commands(project_id)


@app.post("/api/projects/{project_id}/commands")
def add_command(project_id: str, body: CommandIn):
    _project(project_id)
    cid = database.new_id()
    created = database.now_iso()
    cwd = body.cwd.strip() or str(get_settings().target_app_root)
    with database.db() as conn:
        conn.execute(
            """INSERT INTO command_allowlist (id, project_id, name, description, cwd, command, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                cid,
                project_id,
                body.name.strip(),
                body.description.strip(),
                cwd,
                body.command.strip(),
                created,
            ),
        )
    return command_mod.get_command(project_id, cid)


@app.delete("/api/projects/{project_id}/commands/{command_id}")
def delete_command(project_id: str, command_id: str):
    _project(project_id)
    with database.db() as conn:
        conn.execute(
            "DELETE FROM command_allowlist WHERE id = ? AND project_id = ?",
            (command_id, project_id),
        )
    return {"ok": True}


@app.patch("/api/projects/{project_id}/commands/{command_id}")
def update_command(project_id: str, command_id: str, body: CommandIn):
    _project(project_id)
    cwd = body.cwd.strip() or str(get_settings().target_app_root)
    with database.db() as conn:
        updated = conn.execute(
            """UPDATE command_allowlist
               SET name = ?, description = ?, cwd = ?, command = ?
               WHERE id = ? AND project_id = ?""",
            (
                body.name.strip(),
                body.description.strip(),
                cwd,
                body.command.strip(),
                command_id,
                project_id,
            ),
        ).rowcount
    if not updated:
        raise HTTPException(404, "Command not found")
    return command_mod.get_command(project_id, command_id)


@app.post("/api/projects/{project_id}/commands/run")
async def run_command(project_id: str, body: RunCommandIn):
    project = _project(project_id)
    cmd = command_mod.get_command(project_id, body.command_id)
    if not cmd:
        raise HTTPException(404, "Command not allowlisted")

    conversation_id = body.conversation_id
    if conversation_id:
        with database.db() as conn:
            if body.request_text:
                conn.execute(
                    """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
                       VALUES (?, ?, 'user', ?, NULL, ?)""",
                    (database.new_id(), conversation_id, body.request_text, database.now_iso()),
                )
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
                   VALUES (?, ?, 'system', ?, ?, ?)""",
                (
                    database.new_id(),
                    conversation_id,
                    f"Running allowlisted command `{cmd['name']}`: `{cmd['command']}`",
                    json.dumps({"command_id": cmd["id"]}),
                    database.now_iso(),
                ),
            )

    async def events():
        chunks: list[str] = []
        exit_code = None
        async for event in command_mod.run_allowlisted(cmd):
            if event.get("type") == "output":
                chunks.append(event.get("text") or "")
            if event.get("type") == "exit":
                exit_code = event.get("code")
            yield _sse(event)
        output = "".join(chunks)
        summary = await summarize_command_output(project, cmd, output, exit_code)
        yield _sse({"type": "summary", "text": summary})
        if conversation_id:
            with database.db() as conn:
                conn.execute(
                    """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
                       VALUES (?, ?, 'assistant', ?, ?, ?)""",
                    (
                        database.new_id(),
                        conversation_id,
                        f"Command `{cmd['name']}` finished.\n\nSummary: {summary}\n\n```\n{output[-8000:]}\n```",
                        json.dumps({"command_id": cmd["id"]}),
                        database.now_iso(),
                    ),
                )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/api/projects/{project_id}/commands/run-once")
async def run_draft_command(project_id: str, body: RunDraftCommandIn):
    project = _project(project_id)
    cmd = {
        "id": "draft",
        "name": body.name.strip() or "Suggested command",
        "description": body.description.strip(),
        "command": body.command.strip(),
        "cwd": body.cwd.strip() or str(get_settings().target_app_root),
    }
    conversation_id = body.conversation_id
    if conversation_id:
        with database.db() as conn:
            valid = conn.execute(
                "SELECT id FROM conversations WHERE id = ? AND project_id = ?",
                (conversation_id, project_id),
            ).fetchone()
            if not valid:
                raise HTTPException(404, "Conversation not found")
            if body.request_text:
                conn.execute(
                    """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
                       VALUES (?, ?, 'user', ?, NULL, ?)""",
                    (database.new_id(), conversation_id, body.request_text, database.now_iso()),
                )
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
                   VALUES (?, ?, 'system', ?, ?, ?)""",
                (
                    database.new_id(),
                    conversation_id,
                    f"Running one-time approved command `{cmd['name']}`: `{cmd['command']}`",
                    json.dumps({"draft": True}),
                    database.now_iso(),
                ),
            )

    async def events():
        chunks: list[str] = []
        exit_code = None
        async for event in command_mod.run_allowlisted(cmd):
            if event.get("type") == "output":
                chunks.append(event.get("text") or "")
            if event.get("type") == "exit":
                exit_code = event.get("code")
            yield _sse(event)
        output = "".join(chunks)
        summary = await summarize_command_output(project, cmd, output, exit_code)
        yield _sse({"type": "summary", "text": summary})
        if conversation_id:
            with database.db() as conn:
                conn.execute(
                    """INSERT INTO messages (id, conversation_id, role, content, extra_json, created_at)
                       VALUES (?, ?, 'assistant', ?, ?, ?)""",
                    (
                        database.new_id(),
                        conversation_id,
                        f"One-time command `{cmd['name']}` finished.\n\nSummary: {summary}\n\n```\n{output[-8000:]}\n```",
                        json.dumps({"draft": True}),
                        database.now_iso(),
                    ),
                )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/api/projects/{project_id}/logs")
def list_log_paths(project_id: str):
    _project(project_id)
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM log_paths WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return database.rows_to_list(rows)


@app.post("/api/projects/{project_id}/logs")
def add_log_path(project_id: str, body: LogPathIn):
    _project(project_id)
    lid = database.new_id()
    created = database.now_iso()
    with database.db() as conn:
        conn.execute(
            "INSERT INTO log_paths (id, project_id, label, path, created_at) VALUES (?, ?, ?, ?, ?)",
            (lid, project_id, body.label.strip(), str(Path(body.path).expanduser()), created),
        )
        row = conn.execute("SELECT * FROM log_paths WHERE id = ?", (lid,)).fetchone()
    return dict(row)


@app.delete("/api/projects/{project_id}/logs/{log_id}")
def delete_log_path(project_id: str, log_id: str):
    _project(project_id)
    with database.db() as conn:
        conn.execute(
            "DELETE FROM log_paths WHERE id = ? AND project_id = ?",
            (log_id, project_id),
        )
    return {"ok": True}


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")
