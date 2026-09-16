from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path

from . import db as database


def list_commands(project_id: str) -> list[dict]:
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM command_allowlist WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_command(project_id: str, command_id: str) -> dict | None:
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM command_allowlist WHERE id = ? AND project_id = ?",
            (command_id, project_id),
        ).fetchone()
    return dict(row) if row else None


def match_command(project_id: str, name_or_id: str) -> dict | None:
    cmds = list_commands(project_id)
    for c in cmds:
        if c["id"] == name_or_id or c["name"].lower() == name_or_id.lower():
            return c
    return None


async def run_allowlisted(command: dict):
    cwd = Path(command["cwd"]).expanduser()
    if not cwd.is_dir():
        yield {"type": "error", "text": f"Working directory does not exist: {cwd}"}
        return
    try:
        args = shlex.split(command["command"])
    except ValueError as exc:
        yield {"type": "error", "text": f"Invalid command: {exc}"}
        return
    if not args:
        yield {"type": "error", "text": "Empty command"}
        return
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield {"type": "output", "text": line.decode("utf-8", errors="replace")}
    code = await proc.wait()
    yield {"type": "exit", "code": code}
