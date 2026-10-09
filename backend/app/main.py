from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import ApproveRemediationRequest, InvestigationState, StartInvestigationRequest
from app.orchestrator import run_live_investigation, run_replay_investigation
from app.rate_limit import DailyCap, RateLimiter
from app.scenarios import list_scenarios

app = FastAPI(title="INCIDENT ZERO", version="0.1.0")
settings = get_settings()
rate_limiter = RateLimiter(per_minute=settings.rate_limit_per_minute)
daily_cap = DailyCap(cap=settings.live_daily_cap)

_investigations: dict[str, InvestigationState] = {}


@app.on_event("startup")
def _startup() -> None:
    get_settings()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "incident-zero"}


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
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
def public_config() -> dict:
    return {
        "allow_public_live": settings.allow_public_live,
        "live_requires_secret": bool(settings.demo_secret),
        "gemini_configured": bool(settings.gemini_api_key),
        "replay_available": True,
    }


@app.post("/api/investigations", response_model=InvestigationState)
def start_investigation(
    request: Request,
    body: StartInvestigationRequest,
    x_demo_secret: str | None = Header(default=None),
) -> InvestigationState:
    key = _client_key(request)
    if not rate_limiter.allow(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    if body.mode == "replay":
        state = run_replay_investigation(body.scenario_id)
        _investigations[state.investigation_id] = state
        return state

    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="Live investigations require GEMINI_API_KEY. Use mode=replay for offline demo.",
        )

    if not settings.allow_public_live:
        if not settings.demo_secret or x_demo_secret != settings.demo_secret:
            raise HTTPException(
                status_code=403,
                detail="Public live investigations disabled. Use replay mode or provide X-Demo-Secret.",
            )

    if not daily_cap.allow(key):
        raise HTTPException(status_code=429, detail="Daily live investigation cap reached")

    state = run_live_investigation(settings, body.scenario_id)
    _investigations[state.investigation_id] = state
    return state


@app.get("/api/investigations/{investigation_id}", response_model=InvestigationState)
def get_investigation(investigation_id: str) -> InvestigationState:
    state = _investigations.get(investigation_id)
    if state is None and investigation_id == "replay-checkout-p99":
        state = run_replay_investigation("checkout-p99-spike")
    if state is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return state


@app.post("/api/remediation/approve", response_model=InvestigationState)
def approve_remediation(body: ApproveRemediationRequest) -> InvestigationState:
    state = _investigations.get(body.investigation_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    if state.remediation is None:
        raise HTTPException(status_code=400, detail="No remediation plan")
    if not body.approved:
        state.remediation.approved = False
        state.remediation.executed = False
        return state
    state.remediation.approved = True
    state.remediation.executed = True
    state.events.append(
        {
            "phase": "remediation",
            "message": "Simulated remediation executed after explicit approval",
        }
    )
    return state
