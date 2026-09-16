"""Load demo knowledge, repo, skills, commands, and logs for Payments API."""

from __future__ import annotations

from pathlib import Path

from . import commands as command_mod
from . import db as database
from .ingest_code import add_local_repo, index_repo
from .ingest_kb import create_text_doc, upsert_learning_doc
from .paths import APPSENSE_ROOT, ensure_data_dirs
from .skills import save_skill

FIXTURE_ROOT = APPSENSE_ROOT / "fixtures" / "payments-api"
PROJECT_NAME = "Payments API"
SEED_MARKER = "How to restart the Payments API"

KNOWLEDGE = [
    (
        "How to restart the Payments API",
        """# Restart Payments API

Use this when `/health` is degraded, Redis timeouts appear in `api.log`, or PagerDuty `payments-api` is firing.

## Safe restart

1. Confirm the incident in PagerDuty (`payments-api`).
2. Check Redis `payments-cache` and Postgres `payments_prod` before touching the API.
3. Run the allowlisted command **restart-api** (it prints a simulated restart in this demo).
4. Hit `GET http://localhost:8080/health` and expect `{"ok": true, "service": "payments-api"}`.
5. Watch `api.log` for `redis recovered`.

Do not bounce the settlement worker during the 01:15 UTC batch unless settlement itself is stuck.

## Rollback

If health stays degraded after restart, leave the previous Uvicorn workers up and page Payments Platform. The last good image is `payments-api:2.4.1`.
""",
    ),
    (
        "Settlement batch runbook",
        """# Nightly settlement

The `settlement-worker` posts yesterday’s captures to processor **northstar** at **01:15 UTC**.

## Success

Log line: `settlement-worker complete status=posted`. Typical volume is 1.5k–3k items.

## Partial failure

`posted_with_failures` is acceptable if failed ≤ 10 and codes are `processor_timeout`. Those items retry automatically.

`duplicate_capture` must **not** be retried. Open a ticket with item ids (`stl_*`) for finance.

## SLA

Page if the batch has not completed by 01:30 UTC or failed > 25 items.

Retry hint in code: `payments.settlement.should_retry` — only `processor_timeout` and `redis_unavailable`.
""",
    ),
    (
        "Authorization errors (402 and 409)",
        """# Common Payments API errors

| HTTP | Detail | Meaning | Action |
|------|--------|---------|--------|
| 400 | invalid_card_token | Token must start with `tok_` | Merchant integration bug |
| 402 | amount_exceeds_merchant_limit | Amount > $2,500.00 (`250000` cents) | Raise limit in merchant admin or split capture |
| 409 | authorization_expired | Capture after auth TTL | Re-authorize; do not replay capture |

Demo auth id for an expired capture: `auth_expired`.

Healthy auth example: merchant `merch_4421`, amount `1299`, status `approved`, auth id `auth_demo_88421`.
""",
    ),
    (
        "On-call, SLAs, and access",
        """# Payments Platform support

- Service: Payments API v2.4.1, region us-east-1, port 8080
- PagerDuty: `payments-api`
- Slack: `#payments-oncall`
- Datastores: Postgres `payments_prod`, Redis `payments-cache`
- Auth issuer: `https://auth.internal.example/realms/payments`

## SLAs

- API availability 99.9% excluding planned 02:00–02:20 UTC deploys
- p95 authorize < 400ms
- Settlement complete by 01:30 UTC

## Secrets

Webhook secret and DB passwords live in the host env, never in git. `.env.example` lists names only.
""",
    ),
]

HANDBOOK = """# payments-api — code learning

Demo handbook generated for AppSense testing (not a live production scan).

## What it is

FastAPI service that authorizes card payments, captures funds, and posts a nightly settlement batch to processor **northstar**.

## How to run

- `make run` starts a simulated Uvicorn process on port 8080
- Docker: `docker compose up` (api + Postgres + Redis)
- Health: `GET /health`

## Layout

- `payments/api.py` — `/health`, `/v1/authorizations`, `/v1/captures/{auth_id}`, `/v1/settlements/{batch_id}`
- `payments/settlement.py` — cutoff hour 01 UTC, retry rules
- `Makefile` — `run`, `health`, `restart`, `logs`
- `logs/api.log` and `logs/batch.log` — sample incidents

## Operations

- Restart path: `make restart` then `make health`
- Settlement retries: `processor_timeout`, `redis_unavailable`
- Hard failures: `duplicate_capture`, amounts over 250000 cents (HTTP 402)

## Linked knowledge

Restart runbook, settlement runbook, 402/409 error table, on-call SLAs.
"""

SKILLS = [
    (
        "Nightly settlement check",
        "Check yesterday’s settlement batch, summarize failures from the log, and only retry timeouts.",
        """# Nightly settlement check

1. Open the **Settlement batch** log path and find the latest `settlement-worker complete` line.
2. If status is `posted`, reply that the batch is healthy and include `item` counts.
3. If `posted_with_failures`, list each `stl_*` id and error code.
4. Retry only `processor_timeout` / `redis_unavailable`. Never retry `duplicate_capture`.
5. If there is no complete line after 01:30 UTC, recommend the allowlisted **health-check**, then page Payments Platform.
""",
        True,
    ),
    (
        "Restart API after cache errors",
        "If Redis timeouts show in the API log, restart the API with the allowlisted command and confirm health.",
        """# Restart API after cache errors

1. Confirm `redis timeout` or `health degraded=cache` in the API application log.
2. Tell the user you will run **restart-api** (confirm before running).
3. After it finishes, run **health-check**.
4. Look for `redis recovered` in the API log.
5. If health is still degraded, stop and escalate to `#payments-oncall`.
""",
        True,
    ),
]


def _get_or_create_project() -> dict:
    with database.db() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (PROJECT_NAME,),
        ).fetchone()
        if row:
            pid = row["id"]
            conn.execute(
                "UPDATE projects SET description = ? WHERE id = ?",
                (
                    "Card authorization, capture, and nightly settlement (demo data for testing).",
                    pid,
                ),
            )
        else:
            pid = database.new_id()
            conn.execute(
                "INSERT INTO projects (id, name, description, created_at) VALUES (?, ?, ?, ?)",
                (
                    pid,
                    PROJECT_NAME,
                    "Card authorization, capture, and nightly settlement (demo data for testing).",
                    database.now_iso(),
                ),
            )
    with database.db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    return dict(row)


def _already_seeded(project_id: str) -> bool:
    with database.db() as conn:
        row = conn.execute(
            "SELECT id FROM kb_docs WHERE project_id = ? AND title = ?",
            (project_id, SEED_MARKER),
        ).fetchone()
    return row is not None


def _add_command(project_id: str, name: str, description: str, cwd: str, command: str) -> None:
    if command_mod.match_command(project_id, name):
        return
    cid = database.new_id()
    with database.db() as conn:
        conn.execute(
            """INSERT INTO command_allowlist (id, project_id, name, description, cwd, command, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cid, project_id, name, description, cwd, command, database.now_iso()),
        )


def _add_log(project_id: str, label: str, path: str) -> None:
    with database.db() as conn:
        existing = conn.execute(
            "SELECT id FROM log_paths WHERE project_id = ? AND label = ?",
            (project_id, label),
        ).fetchone()
        if existing:
            return
        conn.execute(
            """INSERT INTO log_paths (id, project_id, label, path, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (database.new_id(), project_id, label, path, database.now_iso()),
        )


def seed(force: bool = False) -> dict:
    ensure_data_dirs()
    database.init_db()
    if not FIXTURE_ROOT.is_dir():
        raise FileNotFoundError(f"Missing fixtures at {FIXTURE_ROOT}")

    project = _get_or_create_project()
    project_id = project["id"]
    cwd = str(FIXTURE_ROOT)

    if _already_seeded(project_id) and not force:
        return {"ok": True, "skipped": True, "project_id": project_id}

    docs = []
    if not _already_seeded(project_id):
        for title, body in KNOWLEDGE:
            docs.append(create_text_doc(project_id, title, body))

    with database.db() as conn:
        repo_row = conn.execute(
            "SELECT * FROM repos WHERE project_id = ? AND name = ?",
            (project_id, "payments-api"),
        ).fetchone()
    if repo_row:
        repo = dict(repo_row)
    else:
        repo = add_local_repo(project_id, "payments-api", cwd)

    handbook = upsert_learning_doc(
        project_id,
        "payments-api — code learning",
        HANDBOOK,
        str(FIXTURE_ROOT / "README.md"),
        existing_id=repo.get("scan_doc_id"),
    )
    chunks = index_repo(repo)
    now = database.now_iso()
    with database.db() as conn:
        conn.execute(
            "UPDATE repos SET last_scanned_at = ?, last_indexed_at = ?, scan_doc_id = ? WHERE id = ?",
            (now, now, handbook["id"], repo["id"]),
        )

    for name, goal, body, refined in SKILLS:
        with database.db() as conn:
            exists = conn.execute(
                "SELECT id FROM skills WHERE project_id = ? AND name = ?",
                (project_id, name),
            ).fetchone()
        if not exists:
            save_skill(project_id, name, goal, body, refined)

    _add_command(
        project_id,
        "health-check",
        "Print simulated Payments API health.",
        cwd,
        "make health",
    )
    _add_command(
        project_id,
        "restart-api",
        "Print a simulated API restart (safe demo).",
        cwd,
        "make restart",
    )
    _add_command(
        project_id,
        "tail-api-log",
        "Show the sample API log.",
        cwd,
        "cat logs/api.log",
    )

    _add_log(project_id, "API application log", str(FIXTURE_ROOT / "logs" / "api.log"))
    _add_log(project_id, "Settlement batch log", str(FIXTURE_ROOT / "logs" / "batch.log"))

    return {
        "ok": True,
        "skipped": False,
        "project_id": project_id,
        "knowledge": len(docs),
        "repo_id": repo["id"],
        "code_chunks": chunks,
        "scan_doc_id": handbook["id"],
    }


if __name__ == "__main__":
    print(seed())
