# AppSense ai

**The application that keeps learning with you.**

AppSense is a local support companion for the teams who build, run, and evolve software. It learns the live application — code, notes, scans, skills, and logs — so the product stays understood even when people change.

> Knowledge remains. Always available.  
> If someone leaves tomorrow, the next person can still learn the app, diagnose it, and move it forward.

---

## Why it exists

Traditional support hangs on a few SMEs. When they leave, the map of the application leaves with them. New joiners wait for knowledge transfer. Incidents stall until “the right person” is free. Enhancements restart from scratch because context was never captured.

AppSense holds what the application **is**, how it **runs**, and how it **fails** — in one place, for every team, at any hour. There is no dependency on an individual SME.

```text
Today                         With AppSense
Incident → find the expert    Incident → ask the app
         → wait                        → guided steps
         → hope they remember          → you confirm
```

---

## How it learns

It adopts the app instead of waiting for a handbook.

```text
Code Base → Scan → Knowledge → Skills → Chat
```

Link a repo, drop in notes or files, scan the codebase, and talk to it. The picture of architecture, operations, and playbooks keeps adapting as the application changes.

- **Scan** writes a handbook the whole team can read  
- **Knowledge** stays searchable without a separate wiki project  
- **Skills** capture how work is actually done  

You do not have to author a perfect KB or preset every action. Describe a skill when it is useful. AppSense guides resolution from what it already knows.

---

## Who it serves

One companion across the product lifecycle — without a knowledge-transfer meeting.

| Role | What they get |
|------|----------------|
| **Tech support** | Incidents, logs, and steps from the live system — not a stale ticket comment |
| **Developers** | How it is wired, how to run it, what breaks before you change it |
| **Product owners** | Capabilities and constraints without waiting for a walkthrough |
| **Ops, QA, partners** | The same living knowledge, so handoffs do not reset the story |

Use it to **maintain** today (symptoms → logs → steps → confirm) and to **enhance** tomorrow (idea → how it works → risk → ship informed).

---

## Chat vs Support

| Mode | What it does |
|------|----------------|
| **Chat** | Information only. How it works, what a log means, what you *could* do. No operational actions. |
| **Support** | Skills via `/`, allowlisted commands, step-by-step resolution. Actions still wait for you. |

Type `/` in Support to invoke a skill (for example `/nightly-settlement-check`). The box shows the command; you can add more prompt. The playbook is expanded only when the model is called.

---

## Human in the loop. Always.

AppSense may propose the next step. It does not run free-form shell. Allowlisted commands execute **only after a person confirms**. You keep judgment; it keeps the memory.

---

## What’s in the app

- **Chat / Support** — RAG over knowledge, code, and skills  
- **Learning** — inventory of notes, scans, skills, commands, and logs  
- **Skills** — playbooks you can refine with AI  
- **Code Base** — link a local folder or Git URL, then Scan  
- **Knowledge** — write or upload; it stays in the project  
- **Settings** — LLM, embeddings, log paths, allowlisted commands, delete project  
- **About** — full presentation in a new tab  

A Payments API fixture is included for local testing (`appsense/fixtures/payments-api`).

---

## Quick start

```bash
git clone https://github.com/siva18k/appsense_ai.git
cd appsense_ai/appsense
cp .env.sample .env
# Put your Mistral (or other OpenAI-compatible) API key in .env
```

**Backend** (from `appsense/backend`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend** (from `appsense/frontend`):

```bash
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies `/api` to the backend.

Optional demo data for the Payments API project:

```bash
cd appsense/backend
source .venv/bin/activate
python -m app.seed_demo
```

---

## Configuration

Copy [`appsense/.env.sample`](appsense/.env.sample) to `appsense/.env`. **Do not commit `.env`.**

| Variable | Purpose |
|----------|---------|
| `LLM_BASE_URL` | OpenAI-compatible API (default Mistral) |
| `LLM_API_KEY` | Secret key for chat and embeddings |
| `LLM_MODEL` | e.g. `open-mistral-nemo` |
| `EMBEDDING_MODEL` | e.g. `mistral-embed` |
| `CHROMA_PATH` / `SQLITE_PATH` | Local RAG + metadata |

---

## License

Use and extend for your own application support. Keep secrets in `.env`, never in git.
