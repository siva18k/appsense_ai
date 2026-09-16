from __future__ import annotations

from pathlib import Path

import httpx

from . import db as database
from .ingest_code import index_repo, iter_code_files
from .ingest_kb import upsert_learning_doc
from .settings import get_settings

PRIORITY_NAMES = {
    "readme.md",
    "readme",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "makefile",
    "procfile",
    "pom.xml",
    "build.gradle",
    "cargo.toml",
    "go.mod",
}

MAX_FILES = 220
MAX_CHARS_PER_FILE = 5000
BATCH_CHARS = 14000


def _priority(path: Path) -> int:
    name = path.name.lower()
    if name in PRIORITY_NAMES or name.startswith("readme"):
        return 0
    if path.suffix.lower() in {".md", ".yml", ".yaml", ".toml", ".json"}:
        return 1
    return 2


def _read_files(root: Path) -> list[tuple[str, str]]:
    files = iter_code_files(root)
    files.sort(key=lambda p: (_priority(p), p.as_posix()))
    out: list[tuple[str, str]] = []
    for path in files[:MAX_FILES]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        if len(text) > MAX_CHARS_PER_FILE:
            text = text[:MAX_CHARS_PER_FILE] + "\n...[truncated]"
        out.append((rel, text))
    return out


def _batches(files: list[tuple[str, str]]) -> list[str]:
    batches: list[str] = []
    buf: list[str] = []
    size = 0
    for rel, text in files:
        piece = f"### {rel}\n```\n{text}\n```\n"
        if buf and size + len(piece) > BATCH_CHARS:
            batches.append("\n".join(buf))
            buf = []
            size = 0
        buf.append(piece)
        size += len(piece)
    if buf:
        batches.append("\n".join(buf))
    return batches


def _llm_complete(prompt: str, system: str, max_tokens: int = 2200) -> str:
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
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return ((resp.json().get("choices") or [{}])[0].get("message") or {}).get(
            "content"
        ) or ""


def _skeleton(repo: dict, files: list[tuple[str, str]]) -> str:
    tree = "\n".join(f"- `{rel}`" for rel, _ in files)
    readme = next((body for rel, body in files if Path(rel).name.lower().startswith("readme")), "")
    return f"""# {repo['name']} — code learning

Source: `{repo['source']}`
Local path: `{repo['local_path']}`
Kind: {repo['kind']}
Files scanned: {len(files)}

## File inventory

{tree}

## README / root notes

{readme or '_No README found._'}
"""


def scan_repository(repo: dict) -> dict:
    root = Path(repo["local_path"]).resolve()
    if not root.is_dir():
        raise ValueError(f"Repository path does not exist: {root}")

    files = _read_files(root)
    notes: list[str] = []
    system = (
        "You are documenting a software repository for IT support staff. "
        "Extract facts only from the provided source. Cover purpose, architecture, "
        "entry points, APIs, batch/jobs, how to run, config, services, and operational notes. "
        "Use markdown. Cite file paths in backticks."
    )
    for i, batch in enumerate(_batches(files), start=1):
        prompt = (
            f"Repository: {repo['name']} ({repo['kind']}: {repo['source']})\n"
            f"This is source batch {i}. Summarize key aspects from these files:\n\n{batch}"
        )
        try:
            notes.append(_llm_complete(prompt, system, max_tokens=1600))
        except Exception as exc:
            notes.append(f"_Batch {i} LLM summary failed: {exc}_")

    merged = "\n\n".join(f"## Scan notes (batch {i})\n\n{n}" for i, n in enumerate(notes, start=1))
    final_prompt = (
        f"Write a single support-oriented markdown handbook for `{repo['name']}`.\n"
        f"Path: `{repo['local_path']}` Source: `{repo['source']}`\n"
        "Required sections: Overview, Architecture, How to run, Batch jobs and scheduled work, "
        "APIs and services, Configuration, Key modules and files, Operations (restart, logs, health), "
        "Common support questions.\n"
        "Be specific and cite paths. Merge these notes:\n\n"
        f"{merged[:40000]}"
    )
    try:
        handbook = _llm_complete(final_prompt, system, max_tokens=3500)
    except Exception:
        handbook = ""
    body = handbook.strip() or (_skeleton(repo, files) + "\n\n" + merged)
    if "# " not in body[:80]:
        body = f"# {repo['name']} — code learning\n\n{body}"

    settings = get_settings()
    dest_dir = settings.uploads_path / repo["project_id"] / "scans"
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{repo['id']}-code-learning.md"
    dest = dest_dir / filename
    dest.write_text(body, encoding="utf-8")

    title = f"{repo['name']} — code learning"
    doc = upsert_learning_doc(
        repo["project_id"],
        title,
        body,
        str(dest),
        existing_id=repo.get("scan_doc_id"),
    )
    chunks = index_repo(repo)
    scanned = database.now_iso()
    with database.db() as conn:
        conn.execute(
            "UPDATE repos SET last_scanned_at = ?, last_indexed_at = ?, scan_doc_id = ? WHERE id = ?",
            (scanned, scanned, doc["id"], repo["id"]),
        )
        row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo["id"],)).fetchone()
    return {
        "repo": dict(row),
        "doc": doc,
        "files_read": len(files),
        "code_chunks": chunks,
    }
