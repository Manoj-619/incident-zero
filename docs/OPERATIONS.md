# Running and deploying

## Local development

Python 3.11+ (tested on 3.12), Node 22+, and npm are required. `make install` creates a local virtual environment, installs exact tested Python dependencies, and installs the locked frontend dependencies.

Terminal 1:

```bash
.venv/bin/uvicorn orbit_sentinel.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the backend. No API keys are needed for numerical mode. A frontend-only run uses the three bundled numerical recordings, with fixed parameters and clearly labeled replay approval.

## Docker

```bash
docker compose up --build -d --wait
python scripts/smoke.py
docker compose down
```

The dashboard binds to 127.0.0.1:5173. Backend ports are internal. SQLite uses the `missions` named volume. Both runtime containers use non-root users. `docker compose down` retains the database; `docker compose down -v` removes it. Keep a single backend process and a local volume; the in-memory capacity semaphore is not a distributed scheduler.

## Gemini-assisted mode

Create `.env` from `.env.example` for Compose. Set a fresh `GEMINI_API_KEY`, an available `GEMINI_MODEL`, and a strong random `OPERATOR_SECRET`. Never commit `.env`. For local Uvicorn, export those variables in its shell; Uvicorn does not automatically read the Compose `.env`.

The frontend accepts the operator secret only when Gemini is configured. The key never enters the frontend. Provider availability, model entitlement, quotas, and pricing depend on your Google account. Check the model name if a request fails. No provider key is supplied by this repository, and no successful live Gemini run is claimed in the recorded fixtures.

## HTTP API

- `GET /api/health`: configuration state, never secrets.
- `GET /api/scenarios`: predefined synthetic scenarios.
- `POST /api/missions`: strict mission parameters; returns 202 and run ID.
- `GET /api/missions/{id}`: owned status/result.
- `GET /api/missions/{id}/events?after=0`: fetch-based SSE with cursor support.
- `POST /api/missions/{id}/approve`: atomic, idempotent simulated approval.
- `GET /api/missions/{id}/report`: JSON evidence report.

All mission endpoints require a random 32–128 character ASCII `X-Session-Token`. Unknown and foreign missions both return 404. Gemini starts additionally require `X-Operator-Secret`. Requests with unknown properties, nonfinite numbers, invalid scenarios, or values beyond the configured bounds are rejected.

## Public hosting work still required

This release is a local/demo simulator. Before opening a publicly writable API, add HTTPS, identity and per-user limits, request-body limits at your reverse proxy, controlled operator access, centralized observability, secret management, backups, dependency/image monitoring, and a durable distributed queue if scaling beyond one worker. Global demo limits are not per-user abuse prevention; one visitor can consume the quota. Do not expose Gemini mode anonymously.

The standalone built frontend can be hosted as static files for the recorded demonstration. Fresh calculations require the Python service; a static host alone does not provide the physics backend. No hosted production URL is included in this release.

## Troubleshooting

- **Replay label:** backend `/api/health` was unavailable at page load. Start it and reload.
- **Capacity/quota:** wait for an active run, or wait for the rolling hour quota to expire.
- **Blocked:** the finite candidate search found no verified maneuver under your budget/threshold. Increase the budget or inspect the assumptions; do not bypass verification.
- **Failed provider:** configure a currently available model/key; this failure is intentionally not hidden behind a replay.
- **WebGL unavailable:** numerical tables, risk plots, and reports still work; enable browser hardware acceleration for the globe.
- **Missing capability after closing a tab:** anonymous runs cannot be recovered without that capability. Use the downloaded report for a durable record.
