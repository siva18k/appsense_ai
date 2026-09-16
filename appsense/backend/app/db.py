from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .settings import get_settings

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  extra_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kb_docs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  source_type TEXT NOT NULL,
  filename TEXT,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repos (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  local_path TEXT NOT NULL,
  last_indexed_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS command_allowlist (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  cwd TEXT NOT NULL,
  command TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS log_paths (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  label TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def connect() -> sqlite3.Connection:
    path = get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(repos)").fetchall()}
        if "last_scanned_at" not in cols:
            conn.execute("ALTER TABLE repos ADD COLUMN last_scanned_at TEXT")
        if "scan_doc_id" not in cols:
            conn.execute("ALTER TABLE repos ADD COLUMN scan_doc_id TEXT")
        kb_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_docs)").fetchall()}
        if "updated_at" not in kb_cols:
            conn.execute("ALTER TABLE kb_docs ADD COLUMN updated_at TEXT")
        if "summary" not in kb_cols:
            conn.execute("ALTER TABLE kb_docs ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE kb_docs SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS skills (
              id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL,
              name TEXT NOT NULL,
              goal TEXT NOT NULL,
              body TEXT NOT NULL,
              refined INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              compiled INTEGER NOT NULL DEFAULT 0,
              tested INTEGER NOT NULL DEFAULT 0,
              test_output TEXT NOT NULL DEFAULT '',
              tested_at TEXT,
              FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )"""
        )
        skill_cols = {row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
        for name, definition in (
            ("compiled", "INTEGER NOT NULL DEFAULT 0"),
            ("tested", "INTEGER NOT NULL DEFAULT 0"),
            ("test_output", "TEXT NOT NULL DEFAULT ''"),
            ("tested_at", "TEXT"),
        ):
            if name not in skill_cols:
                conn.execute(f"ALTER TABLE skills ADD COLUMN {name} {definition}")
        conn.commit()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
