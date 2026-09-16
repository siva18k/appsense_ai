# AppSense (this folder)

Local app lives here. The project story, why it exists, and full setup are in the **[root README](../README.md)**.

```bash
cp .env.sample .env   # then add your API key — never commit .env
```


cd backend
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

cd frontend; npm run dev
