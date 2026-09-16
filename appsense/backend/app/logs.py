from __future__ import annotations

from pathlib import Path

from . import db as database


def _allowed_log_paths(project_id: str) -> list[dict]:
    with database.db() as conn:
        rows = conn.execute(
            "SELECT * FROM log_paths WHERE project_id = ?", (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def _is_allowed(path: Path, allowed: list[dict]) -> dict | None:
    resolved = path.resolve()
    for item in allowed:
        configured = Path(item["path"]).expanduser().resolve()
        if resolved == configured:
            return item
        if configured.is_dir() and resolved.is_relative_to(configured):
            return item
    return None


def tail_logs(project_id: str, path: str | None, lines: int = 120) -> dict:
    allowed = _allowed_log_paths(project_id)
    if not allowed:
        return {"ok": False, "error": "No log paths configured for this project."}
    target: Path | None = None
    matched = None
    if path:
        target = Path(path).expanduser()
        matched = _is_allowed(target, allowed)
        if not matched:
            return {
                "ok": False,
                "error": "That log path is not in project settings.",
                "configured": [{"label": a["label"], "path": a["path"]} for a in allowed],
            }
    else:
        matched = allowed[0]
        target = Path(matched["path"]).expanduser()
    resolved = target.resolve()
    if resolved.is_dir():
        candidates = sorted(resolved.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return {"ok": False, "error": f"No .log files in {resolved}"}
        resolved = candidates[0]
    if not resolved.is_file():
        return {"ok": False, "error": f"Log file not found: {resolved}"}
    text = resolved.read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(text.splitlines()[-max(1, min(lines, 400)) :])
    return {
        "ok": True,
        "label": matched["label"],
        "path": str(resolved),
        "text": tail,
    }
