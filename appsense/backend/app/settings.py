from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key

from .paths import APPSENSE_ROOT, ENV_PATH, ensure_data_dirs

SECRET_KEYS = {"LLM_API_KEY"}
PUBLIC_KEYS = (
    "LLM_BASE_URL",
    "LLM_MODEL",
    "EMBEDDING_MODEL",
    "CHROMA_PATH",
    "SQLITE_PATH",
    "UPLOADS_PATH",
    "REPOS_PATH",
    "DEFAULT_COMMAND_CWD",
    "DEFAULT_COMMAND_PYTHON",
    "TARGET_APP_ROOT",
    "TARGET_APP_PYTHON",
    "TARGET_APP_ENV_FILE",
)


def _reload_env() -> None:
    ensure_data_dirs()
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)


def _abs_from_root(value: str, default: str) -> Path:
    raw = value or default
    path = Path(raw)
    if not path.is_absolute():
        path = APPSENSE_ROOT / path
    return path.resolve()


def _abs_from_base(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


@dataclass
class AppSettings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    embedding_model: str
    chroma_path: Path
    sqlite_path: Path
    uploads_path: Path
    repos_path: Path
    default_command_cwd: Path
    default_command_python: str
    target_app_root: Path
    target_app_python: str
    target_app_env_file: Path | None
    has_api_key: bool


def get_settings() -> AppSettings:
    _reload_env()
    chroma = _abs_from_root(os.getenv("CHROMA_PATH", ""), "./data/chroma")
    sqlite = _abs_from_root(os.getenv("SQLITE_PATH", ""), "./data/appsense.db")
    uploads = _abs_from_root(os.getenv("UPLOADS_PATH", ""), "./data/uploads")
    repos = _abs_from_root(os.getenv("REPOS_PATH", ""), "./data/repos")
    default_command_cwd = _abs_from_root(os.getenv("DEFAULT_COMMAND_CWD", ""), ".")
    target_app_root = _abs_from_root(os.getenv("TARGET_APP_ROOT", ""), str(default_command_cwd))
    target_python_raw = os.getenv("TARGET_APP_PYTHON", "").strip()
    target_app_python = str(_abs_from_base(target_python_raw, target_app_root)) if target_python_raw else os.getenv(
        "DEFAULT_COMMAND_PYTHON", sys.executable
    )
    target_env_raw = os.getenv("TARGET_APP_ENV_FILE", "").strip()
    target_app_env_file = _abs_from_base(target_env_raw, target_app_root) if target_env_raw else None
    for p in (chroma, uploads, repos, sqlite.parent):
        p.mkdir(parents=True, exist_ok=True)
    key = os.getenv("LLM_API_KEY", "")
    return AppSettings(
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.mistral.ai/v1").rstrip("/"),
        llm_api_key=key,
        llm_model=os.getenv("LLM_MODEL", "open-mistral-nemo"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "mistral-embed"),
        chroma_path=chroma,
        sqlite_path=sqlite,
        uploads_path=uploads,
        repos_path=repos,
        default_command_cwd=default_command_cwd,
        default_command_python=os.getenv("DEFAULT_COMMAND_PYTHON", sys.executable),
        target_app_root=target_app_root,
        target_app_python=target_app_python,
        target_app_env_file=target_app_env_file,
        has_api_key=bool(key.strip()),
    )


def public_settings_dict() -> dict:
    s = get_settings()
    return {
        "llm_base_url": s.llm_base_url,
        "llm_model": s.llm_model,
        "embedding_model": s.embedding_model,
        "chroma_path": str(s.chroma_path),
        "sqlite_path": str(s.sqlite_path),
        "uploads_path": str(s.uploads_path),
        "repos_path": str(s.repos_path),
        "default_command_cwd": str(s.default_command_cwd),
        "default_command_python": s.default_command_python,
        "target_app_root": str(s.target_app_root),
        "target_app_python": s.target_app_python,
        "target_app_env_file": str(s.target_app_env_file) if s.target_app_env_file else "",
        "has_api_key": s.has_api_key,
        "env_path": str(ENV_PATH),
    }


def update_env(updates: dict[str, str | None]) -> dict:
    if not ENV_PATH.exists():
        ENV_PATH.write_text("# AppSense local settings\n", encoding="utf-8")
    allowed = set(PUBLIC_KEYS) | SECRET_KEYS
    current = dotenv_values(ENV_PATH)
    for key, value in updates.items():
        if key not in allowed:
            continue
        if value is None:
            continue
        if key in SECRET_KEYS and value.strip() == "":
            continue
        set_key(str(ENV_PATH), key, value.strip())
        current[key] = value.strip()
    _reload_env()
    return public_settings_dict()
