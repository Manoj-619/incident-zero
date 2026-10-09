# INCIDENT ZERO

**Evidence-driven adversarial incident investigation.** A hardened demonstration service using React, FastAPI, and Gemini on synthetic checkout telemetry.

The Investigator selects allowlisted Python tools, then evaluates their outputs. The Skeptic evaluates competing explanations. The Experimenter selects a deterministic intervention. The Judge cites collected evidence. Every stage is bounded; malformed provider output or unsupported citations stop the investigation. No diagnosis is silently substituted.

## Run locally

Python 3.12 and Node 22:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
cd backend
uvicorn app.main:app --port 8000 --no-proxy-headers
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Replay works without a key. It is an **illustrative scripted example**, not a previously recorded LLM investigation. Reset creates a fresh view; running again creates a separate investigation.

## Controlled live access

Configure `GEMINI_API_KEY` and a strong random `DEMO_SECRET` in the server environment. Keep `ALLOW_PUBLIC_LIVE=false`. Enter the operator secret in the password input at runtime. It is held in React memory only, never embedded in a Vite bundle. Use HTTPS for remote access; this shared operator secret is appropriate for a controlled demo, not enterprise identity management. No provider key is ever sent to the browser.

`GEMINI_MODEL` defaults to `gemini-3.8-flash`; choose a model available in your account. The client uses the official `google-genai` SDK, JSON output, an output-token cap, a 20-second request timeout, and a single provider attempt. Account/model availability and paid live inference require separate verification with your key.

Clients generate a random per-tab capability in session storage, sent as `X-Session-Token`. The database stores its hash. Read and approval endpoints require the same capability. Losing it loses access to that tab's investigation. This is anonymous session isolation, not user authentication.

## Limits and persistence

SQLite stores investigations for 24 hours and atomically reserves quotas across processes on **one host using the same database file**. The live cap is global, defaults to five starts per rolling 24-hour window, and includes failed attempts. IP throttling uses the direct peer; forwarded headers are ignored. Behind a reverse proxy, visitors share its rate bucket, a conservative default. Set rate limiting and body limits at the trusted edge before increasing traffic.

Investigations allow at most eight LLM requests and twelve Python tool/experiment invocations. Typical successful workflow makes five LLM requests. A wall deadline is checked between calls; an in-flight call can extend it by up to the provider timeout. Requests complete synchronously; events include actual stage timestamps, but are delivered after completion, not streamed.

These controls bound requests and tokens, **not INR spend**. Provider pricing, input/output usage, and billing must be checked separately. Set provider billing controls for your ₹500 budget; keep public access in replay. Multiple hosts need a shared transactional quota store and investigation database. Do not run SQLite over a network filesystem.

## Evidence and simulations

Runtime scenario objects contain no answer key; evaluation truth exists only under `backend/tests`, excluded from the backend image. Tool arguments are allowlisted, and evidence IDs hash tool name, arguments and output. Model citations must exist in the collected ledger. This verifies provenance, **not whether an inference logically follows**; review the cited output.

Simulation uses an explicitly approximate additive latency model:

`checkout_after = max(0, checkout_before - pool_wait - lock_wait) + pool_after + lock_after`

Increasing pool capacity halves pool wait; shortening lock windows reduces lock wait to 25%. Results come from Python, without shell execution or model-generated code. These assumed effects do not independently prove real-world causality. Remediation is available only for a cited, sufficiently confident verdict and a tested intervention improving modeled latency by at least 10%. Approval applies simulated recovery values atomically and idempotently; it never touches real infrastructure.

## Verification

```bash
python -m pytest backend/tests -q
pip check
cd frontend
npm ci
npm run build
```

CI runs backend tests, dependency validation, the frontend build, and container builds. Tests cover session isolation, atomic quotas, explicit and idempotent approval, unsupported evidence, tool inputs, ground-truth separation, simulation math, provider failures, and a mocked complete live workflow. Mocked provider tests are not evidence that live Gemini works.

## Containers and deployment

```bash
cp .env.example .env
# Edit server settings; leave keys out of Git.
docker compose up --build -d
```

Visit http://localhost:5173. Compose keeps the backend internal, runs it as a non-root user, and persists state in a named volume. Frontend uses a committed npm lockfile. Backend image excludes tests and evaluation truth. Nginx limits body size, adds browser security headers, and waits up to 150 seconds for investigation responses.

For remote hosting, terminate HTTPS with your hosting provider or a trusted reverse proxy, route it to the frontend, and adjust the loopback binding deliberately. Back up the state volume and restrict access to it. Verify `/health`, replay, isolated approval, and a controlled live investigation before sharing the URL. This React/FastAPI application is not a Streamlit Community Cloud project.

## Remaining production work

This remains a **hardened simulation demo**, not a production SRE platform. Enterprise rollout needs authenticated users and authorization, real telemetry adapters, queue-based execution, shared storage, audit retention, observability, load testing, key rotation, model evaluations, and independent security review. The current fixture has only three log entries and aggregate metrics; it is not a rich production telemetry dataset. No production infrastructure integration or deployment is claimed.
