from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pathspec

from . import db as database
from .rag import chunk_text, code_collection, delete_by_metadata, upsert_chunks
from .settings import get_settings

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".chroma",
    "data",
    ".next",
    "target",
    ".idea",
    ".tox",
}

TEXT_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".mdx",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".bash",
    ".zsh",
    ".sql",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".css",
    ".scss",
    ".html",
    ".xml",
    ".txt",
    ".env.example",
    ".gitignore",
    ".dockerignore",
}

MAX_FILE_BYTES = 400_000


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gi = root / ".gitignore"
    if not gi.exists():
        return None
    lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def iter_code_files(root: Path) -> list[Path]:
    spec = _load_gitignore(root)
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        current = Path(dirpath)
        for name in filenames:
            path = current / name
            rel = path.relative_to(root).as_posix()
            if spec and spec.match_file(rel):
                continue
            suffix = path.suffix.lower()
            if suffix not in TEXT_EXTS and name not in {"Dockerfile", "Makefile", "Procfile"}:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(path)
    return files


def index_repo(repo: dict) -> int:
    root = Path(repo["local_path"]).resolve()
    if not root.exists():
        return 0
    delete_by_metadata(code_collection(), {"repo_id": repo["id"]})
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    for path in iter_code_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        chunks = chunk_text(text, chunk_size=1100, overlap=150)
        for i, chunk in enumerate(chunks):
            ids.append(f"{repo['id']}:{rel}:{i}")
            docs.append(chunk)
            metas.append(
                {
                    "project_id": repo["project_id"],
                    "repo_id": repo["id"],
                    "repo_name": repo["name"],
                    "path": rel,
                    "abs_path": str(path),
                    "chunk_index": i,
                }
            )
    upsert_chunks(code_collection(), ids, docs, metas)
    with database.db() as conn:
        conn.execute(
            "UPDATE repos SET last_indexed_at = ? WHERE id = ?",
            (database.now_iso(), repo["id"]),
        )
    return len(ids)


def delete_repo_vectors(repo_id: str) -> None:
    delete_by_metadata(code_collection(), {"repo_id": repo_id})


def clone_or_pull(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        subprocess.run(
            ["git", "-C", str(dest), "pull", "--ff-only"],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"Clone destination is not empty: {dest}")
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )


def add_local_repo(project_id: str, name: str, local_path: str) -> dict:
    path = Path(local_path).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("Local path is not a directory")
    repo_id = database.new_id()
    created = database.now_iso()
    display = name.strip() or path.name
    with database.db() as conn:
        conn.execute(
            """INSERT INTO repos (id, project_id, name, kind, source, local_path, last_indexed_at, created_at)
               VALUES (?, ?, ?, 'local', ?, ?, NULL, ?)""",
            (repo_id, project_id, display, str(path), str(path), created),
        )
    repo = {
        "id": repo_id,
        "project_id": project_id,
        "name": display,
        "kind": "local",
        "source": str(path),
        "local_path": str(path),
        "last_indexed_at": None,
        "created_at": created,
    }
    with database.db() as conn:
        row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
    return dict(row)


def add_remote_repo(project_id: str, name: str, url: str) -> dict:
    settings = get_settings()
    repo_id = database.new_id()
    dest = settings.repos_path / project_id / repo_id
    clone_or_pull(url.strip(), dest)
    created = database.now_iso()
    display = name.strip() or url.rstrip("/").split("/")[-1].removesuffix(".git")
    with database.db() as conn:
        conn.execute(
            """INSERT INTO repos (id, project_id, name, kind, source, local_path, last_indexed_at, created_at)
               VALUES (?, ?, ?, 'remote', ?, ?, NULL, ?)""",
            (repo_id, project_id, display, url.strip(), str(dest), created),
        )
    repo = {
        "id": repo_id,
        "project_id": project_id,
        "name": display,
        "kind": "remote",
        "source": url.strip(),
        "local_path": str(dest),
        "last_indexed_at": None,
        "created_at": created,
    }
    with database.db() as conn:
        row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
    return dict(row)
