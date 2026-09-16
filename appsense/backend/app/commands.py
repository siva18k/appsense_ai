from __future__ import annotations

import asyncio
import json
import os
import shlex
from pathlib import Path

from . import db as database
from .settings import get_settings


def resolve_cwd(value: str | None) -> str:
    raw = (value or "").strip()
    if raw.lower() in {"", ".", "project_root", "app_root", "appsense_root"}:
        return str(get_settings().target_app_root)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(get_settings().target_app_root) / path
    return str(path.resolve())


def resolve_args(command: str) -> list[str]:
    args = shlex.split(command)
    if args and args[0].lower() in {"python", "python3"}:
        args[0] = get_settings().target_app_python
    return args


def command_environment() -> dict[str, str]:
    settings = get_settings()
    environment = dict(os.environ)
    if settings.target_app_env_file and settings.target_app_env_file.is_file():
        from dotenv import dotenv_values

        for key, value in dotenv_values(settings.target_app_env_file).items():
            if value is not None:
                environment[key] = value
    return environment


def list_commands(project_id: str) -> list[dict]:
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM command_allowlist WHERE project_id = ? ORDER BY name",
            (project_id,),
        ).fetchall()
    commands = [dict(r) for r in rows]
    for command in commands:
        command["cwd"] = resolve_cwd(command.get("cwd"))
    return commands


def get_command(project_id: str, command_id: str) -> dict | None:
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM command_allowlist WHERE id = ? AND project_id = ?",
            (command_id, project_id),
        ).fetchone()
    if not row:
        return None
    command = dict(row)
    command["cwd"] = resolve_cwd(command.get("cwd"))
    return command


def match_command(project_id: str, name_or_id: str) -> dict | None:
    cmds = list_commands(project_id)
    for c in cmds:
        if c["id"] == name_or_id or c["name"].lower() == name_or_id.lower():
            return c
    return None


async def run_allowlisted(command: dict):
    cwd = Path(resolve_cwd(command.get("cwd")))
    if not cwd.is_dir():
        yield {"type": "error", "text": f"Working directory does not exist: {cwd}"}
        return
    raw_command = command["command"].strip()
    if not raw_command:
        yield {"type": "error", "text": "Empty command"}
        return
    shell_syntax = any(token in raw_command for token in ("&&", "||", ";", "|", ">", "<"))
    try:
        args = resolve_args(raw_command) if not shell_syntax else []
    except ValueError as exc:
        yield {"type": "error", "text": f"Invalid command: {exc}"}
        return
    try:
        process_kwargs = {
            "cwd": str(cwd),
            "env": command_environment(),
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if shell_syntax:
            proc = await asyncio.create_subprocess_shell(raw_command, **process_kwargs)
        else:
            proc = await asyncio.create_subprocess_exec(*args, **process_kwargs)
    except OSError as exc:
        yield {"type": "error", "text": f"Could not start command: {exc}"}
        return
    yield {"type": "status", "text": f"Process started (pid {proc.pid}). Waiting for output..."}
    assert proc.stdout
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield {"type": "output", "text": line.decode("utf-8", errors="replace")}
        code = await proc.wait()
        yield {"type": "exit", "code": code}
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()
        raise
