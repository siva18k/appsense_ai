"""Nightly settlement worker (demo)."""

from datetime import datetime, timezone


CUTOFF_HOUR = 1
PROCESSOR = "northstar"


def window_for(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now.date()).isoformat()


def should_retry(error_code: str) -> bool:
    return error_code in {"processor_timeout", "redis_unavailable"}


def restart_hint() -> str:
    return "systemctl restart payments-settlement && make health"
