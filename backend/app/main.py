import hashlib
import secrets
import uuid
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.models import (
    ApproveRemediationRequest,
    InvestigationState,
    StartInvestigationRequest,
)
from app.orchestrator import run_live_investigation, run_replay_investigation
from app.scenarios import list_scenarios, get_scenario
from app.store import Store

app = FastAPI(title="INCIDENT ZERO", version="0.2.0")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Demo-Secret", "X-Session-Token"],
)


def store():
    return Store(get_settings().database_path)


def owner(token):
    if not token or not 32 <= len(token) <= 128:
        raise HTTPException(401, "A client session token is required")
    return hashlib.sha256(token.encode()).hexdigest()


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": "incident-zero"}


@app.get("/api/scenarios")
def scenarios():
    return [
        {
            "scenario_id": s.scenario_id,
            "title": s.title,
            "public_summary": s.public_summary,
            "alert_text": s.alert_text,
        }
        for s in list_scenarios()
    ]


@app.get("/api/config/public")
def public_config():
    s = get_settings()
    return {
        "allow_public_live": s.allow_public_live,
        "live_requires_secret": bool(s.demo_secret),
        "gemini_configured": bool(s.gemini_api_key),
        "replay_available": True,
    }


@app.post("/api/investigations", response_model=InvestigationState)
def start_investigation(
    request: Request,
    body: StartInvestigationRequest,
    x_demo_secret: str | None = Header(default=None),
    x_session_token: str | None = Header(default=None),
):
    identity = owner(x_session_token)
    s, db = get_settings(), store()
    key = request.client.host if request.client else "unknown"
    if not db.allow("rate:" + key, s.rate_limit_per_minute, 60):
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})
    try:
        get_scenario(body.scenario_id)
    except KeyError:
        raise HTTPException(404, "Unknown scenario")
    if body.mode == "replay":
        state = run_replay_investigation(body.scenario_id)
        state.investigation_id = str(uuid.uuid4())
    else:
        if not s.gemini_api_key:
            raise HTTPException(503, "Live AI unavailable; use replay")
        if not s.allow_public_live and (
            not s.demo_secret
            or not secrets.compare_digest(x_demo_secret or "", s.demo_secret)
        ):
            raise HTTPException(403, "Live access requires the operator secret")
        if not db.allow("live:global", s.live_daily_cap, 86400):
            raise HTTPException(429, "Global live investigation cap reached")
        state = run_live_investigation(s, body.scenario_id)
    db.save(state, identity)
    return state


@app.get("/api/investigations/{investigation_id}", response_model=InvestigationState)
def get_investigation(
    investigation_id: str, x_session_token: str | None = Header(default=None)
):
    state = store().get(investigation_id, owner(x_session_token))
    if not state:
        raise HTTPException(404, "Investigation not found")
    return state


@app.post("/api/remediation/approve", response_model=InvestigationState)
def approve_remediation(
    body: ApproveRemediationRequest, x_session_token: str | None = Header(default=None)
):
    try:
        state = store().approve(
            body.investigation_id, owner(x_session_token), body.approved
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not state:
        raise HTTPException(404, "Investigation not found")
    return state
