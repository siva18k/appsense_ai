# AppSense

Local support console for IT applications: project-scoped chat over knowledge and code (ChromaDB + sentence-transformers), a learning article browser, and allowlisted commands that only run after you confirm.

## Setup

```bash
cd appsense
cp .env.example .env
# Edit .env: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, EMBEDDING_MODEL
```

Backend:

```bash
cd appsense/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run uvicorn from `appsense/backend` so the `app` package imports correctly.

Frontend:

```bash
cd appsense/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 — Vite proxies `/api` to the backend.

## Usage

1. Create a project in the left sidebar.
2. Add notes or PDFs under Knowledge base (they appear in Learning).
3. Link a local folder or clone a remote Git URL under Code Base.
4. In Settings, set the LLM endpoint and embedding model; keep the API key in `.env`.
5. Optionally add log file paths and allowlisted commands (name, cwd, command).
6. Chat: ask for an overview, how to run a batch, or to run an allowlisted command (Confirm before it executes).

Embeddings use ChromaDB’s ONNX MiniLM by default (same family as `all-MiniLM-L6-v2`). To use another Hugging Face sentence-transformer, install the extra package when you have disk space:

```bash
pip install sentence-transformers
```

Then set `EMBEDDING_MODEL` in `.env`.
