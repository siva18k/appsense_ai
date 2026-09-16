from __future__ import annotations

import re

import httpx

from . import commands as command_mod
from . import db as database
from .ingest_kb import make_summary
from .rag import (
    chunk_text,
    code_collection,
    delete_by_metadata,
    kb_collection,
    query_project,
    skills_collection,
    upsert_chunks,
)
from .settings import get_settings


def index_skill(skill: dict) -> int:
    delete_by_metadata(skills_collection(), {"skill_id": skill["id"]})
    text = f"# {skill['name']}\n\n{skill.get('goal') or ''}\n\n{skill.get('body') or ''}"
    chunks = chunk_text(text)
    ids = [f"{skill['id']}:{i}" for i in range(len(chunks))]
    metas = [
        {
            "project_id": skill["project_id"],
            "skill_id": skill["id"],
            "title": skill["name"],
            "source_type": "skill",
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    upsert_chunks(skills_collection(), ids, chunks, metas)
    return len(chunks)


def delete_skill_vectors(skill_id: str) -> None:
    delete_by_metadata(skills_collection(), {"skill_id": skill_id})


def list_skills(project_id: str) -> list[dict]:
    with database.db() as conn:
        rows = conn.execute(
            """SELECT id, project_id, name, goal, body, refined, created_at, updated_at,
                      substr(body, 1, 280) AS excerpt
               FROM skills WHERE project_id = ?
               ORDER BY updated_at DESC""",
            (project_id,),
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["summary"] = make_summary(d.get("goal") or d.get("excerpt") or "")
        d["refined"] = bool(d.get("refined"))
        out.append(d)
    return out


def get_skill(project_id: str, skill_id: str) -> dict | None:
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM skills WHERE id = ? AND project_id = ?",
            (skill_id, project_id),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["refined"] = bool(d.get("refined"))
    return d


def save_skill(
    project_id: str,
    name: str,
    goal: str,
    body: str,
    refined: bool,
    skill_id: str | None = None,
) -> dict:
    now = database.now_iso()
    display = name.strip() or "Untitled skill"
    content = (body or goal).strip()
    if skill_id:
        existing = get_skill(project_id, skill_id)
        if not existing:
            raise ValueError("Skill not found")
        with database.db() as conn:
            conn.execute(
                """UPDATE skills SET name = ?, goal = ?, body = ?, refined = ?, updated_at = ?
                   WHERE id = ?""",
                (display, goal.strip(), content, 1 if refined else 0, now, skill_id),
            )
        skill = get_skill(project_id, skill_id)
    else:
        skill_id = database.new_id()
        with database.db() as conn:
            conn.execute(
                """INSERT INTO skills
                   (id, project_id, name, goal, body, refined, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (skill_id, project_id, display, goal.strip(), content, 1 if refined else 0, now, now),
            )
        skill = get_skill(project_id, skill_id)
    assert skill
    index_skill(skill)
    return skill


def delete_skill(project_id: str, skill_id: str) -> None:
    with database.db() as conn:
        conn.execute(
            "DELETE FROM skills WHERE id = ? AND project_id = ?",
            (skill_id, project_id),
        )
    delete_skill_vectors(skill_id)


def reindex_project_skills(project_id: str) -> int:
    total = 0
    for skill in list_skills(project_id):
        full = get_skill(project_id, skill["id"])
        if full:
            total += index_skill(full)
    return total


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _llm_complete(prompt: str, system: str) -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is not set")
    url = f"{settings.llm_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "temperature": 0.15,
        "max_tokens": 2800,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _project_context(project_id: str, goal: str) -> str:
    kb = query_project(kb_collection(), project_id, goal, n_results=8)
    code = query_project(code_collection(), project_id, goal, n_results=4)
    cmds = command_mod.list_commands(project_id)
    with database.db() as conn:
        project = dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        repos = [
            dict(r)
            for r in conn.execute(
                "SELECT name, kind, source FROM repos WHERE project_id = ?", (project_id,)
            ).fetchall()
        ]
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT label, path FROM log_paths WHERE project_id = ?", (project_id,)
            ).fetchall()
        ]
    kb_block = "\n\n".join(
        f"- {(h.get('metadata') or {}).get('title')}: {(h.get('text') or '')[:500]}" for h in kb
    ) or "(none)"
    code_block = "\n\n".join(
        f"- {(h.get('metadata') or {}).get('path')}: {(h.get('text') or '')[:400]}" for h in code
    ) or "(none)"
    cmd_block = "\n".join(
        f"- {c['name']}: {c['description']} | `{c['command']}` cwd={c['cwd']}" for c in cmds
    ) or "(none — do not invent shell commands)"
    repo_block = "\n".join(f"- {r['name']} ({r['kind']}) {r['source']}" for r in repos) or "(none)"
    log_block = "\n".join(f"- {l['label']}: {l['path']}" for l in logs) or "(none)"
    return f"""Project: {project.get('name')} — {project.get('description') or ''}

Allowlisted commands (only these may be used as executable steps):
{cmd_block}

Repos:
{repo_block}

Log paths:
{log_block}

Retrieved knowledge:
{kb_block}

Retrieved code:
{code_block}
"""


def refine_skill(project_id: str, name: str, goal: str) -> str:
    context = _project_context(project_id, goal)
    system = (
        "You write agent skill playbooks as markdown for an application-support assistant. "
        "Use only the provided project knowledge, code, and allowlisted commands. "
        "Never invent production hostnames, secrets, or unlisted shell commands. "
        "If a step needs a command that is not allowlisted, say the operator must add it in Settings."
    )
    prompt = f"""Turn the user's skill idea into a detailed LLM-ready markdown playbook for this app.

Skill name: {name.strip() or "Untitled skill"}
User idea:
{goal.strip()}

{context}

Required sections:
# <skill name>
## Goal
## When to use
## Inputs
## Steps (numbered, concrete, cite file paths or allowlisted command names)
## Tools and commands
## Success criteria
## If it fails
## Notes for the model (how to answer follow-up questions)

Write markdown only."""
    return _strip_fence(_llm_complete(prompt, system))
