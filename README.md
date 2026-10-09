# INCIDENT ZERO

Multi-agent incident investigation demo: **Hypothesis Battle** + **Counterfactual Lab**.

## Quick start (local)

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and click **Run replay demo** (no API key).

## Live LLM investigations

Copy `.env.example` to `.env` in the repo root and set:

- `GEMINI_API_KEY` — server-side only
- `ALLOW_PUBLIC_LIVE=false` (default) — public visitors get replay only
- `DEMO_SECRET` — pass as `X-Demo-Secret` header or `VITE_DEMO_SECRET` for private live demos

## Tests

```bash
cd backend && pytest -q
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```
