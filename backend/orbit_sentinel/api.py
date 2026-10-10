"""Single-worker local/demo API with bounded computation, SSE, and private run capabilities."""

import asyncio
import json
import os
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from .agents.gemini import ProviderUnavailable
from .agents.workflow import MissionTimeout, run_mission
from .models import MissionRequest
from .scenarios import catalog
from .store import Conflict, Journal, NotFound


def create_app(database_path: str | None = None):
    journal = Journal(database_path or os.getenv("DATABASE_PATH", "./data/missions.sqlite3"))
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orbit-mission")
    capacity = threading.BoundedSemaphore(2)

    @asynccontextmanager
    async def lifespan(_app):
        journal.recover()
        yield
        executor.shutdown(wait=True, cancel_futures=False)

    application = FastAPI(title="ORBIT SENTINEL", version="0.1.0", lifespan=lifespan)
    application.state.journal = journal

    def owned(identifier: str, token: str):
        try:
            return journal.get(identifier, token)
        except NotFound:
            raise HTTPException(404, "Mission not found.") from None

    def validate_token(token: str):
        if not 32 <= len(token) <= 128 or not token.isascii():
            raise HTTPException(400, "Provide a 32-128 character ASCII X-Session-Token capability.")

    def worker(identifier: str, parameters: MissionRequest):
        try:
            result = run_mission(
                parameters,
                lambda role, kind, payload: journal.event(identifier, role, kind, payload),
            )
            journal.finish(identifier, result=result)
        except (ProviderUnavailable, MissionTimeout) as error:
            journal.event(identifier, "mission_control", "error", {"message": str(error)})
            journal.finish(identifier, error=str(error))
        except Exception:
            journal.event(
                identifier,
                "mission_control",
                "error",
                {"message": "Numerical mission failed. No approval is available."},
            )
            journal.finish(identifier, error="Numerical mission failed. No approval is available.")
        finally:
            capacity.release()

    @application.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "simulation_only": True,
            "gemini_configured": bool(os.getenv("GEMINI_API_KEY") and os.getenv("OPERATOR_SECRET")),
        }

    @application.get("/api/scenarios")
    def scenarios():
        return catalog()

    @application.post("/api/missions", status_code=202)
    def start(
        parameters: MissionRequest,
        x_session_token: Annotated[str, Header()],
        x_operator_secret: Annotated[str | None, Header()] = None,
    ):
        validate_token(x_session_token)
        if parameters.mode == "gemini":
            secret = os.getenv("OPERATOR_SECRET")
            if (
                not secret
                or not x_operator_secret
                or not secrets.compare_digest(secret, x_operator_secret)
            ):
                raise HTTPException(403, "Gemini mode requires the configured operator secret.")
            if not os.getenv("GEMINI_API_KEY"):
                raise HTTPException(503, "Gemini is not configured.")
        if not capacity.acquire(blocking=False):
            raise HTTPException(
                429, "Mission capacity reached. Retry when the active mission completes."
            )
        try:
            identifier = journal.create(x_session_token, parameters.model_dump())
            executor.submit(worker, identifier, parameters)
        except Conflict as error:
            capacity.release()
            raise HTTPException(429, str(error)) from None
        except Exception:
            capacity.release()
            raise
        return {"id": identifier, "status": "running"}

    @application.get("/api/missions/{identifier}")
    def mission(identifier: str, x_session_token: Annotated[str, Header()]):
        validate_token(x_session_token)
        return owned(identifier, x_session_token)

    @application.get("/api/missions/{identifier}/events")
    async def events(
        identifier: str,
        request: Request,
        x_session_token: Annotated[str, Header()],
        after: int = Query(default=0, ge=0),
    ):
        validate_token(x_session_token)
        owned(identifier, x_session_token)

        async def stream():
            cursor = after
            for _ in range(180):
                if await request.is_disconnected():
                    return
                run = owned(identifier, x_session_token)
                batch = journal.events(identifier, cursor)
                for event in batch:
                    cursor = event["sequence"]
                    yield f"id: {cursor}\nevent: mission\ndata: {json.dumps(event)}\n\n"
                if run["status"] != "running":
                    yield f"event: complete\ndata: {json.dumps({'status': run['status']})}\n\n"
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.post("/api/missions/{identifier}/approve")
    def approve(identifier: str, x_session_token: Annotated[str, Header()]):
        validate_token(x_session_token)
        try:
            return journal.approve(identifier, x_session_token)
        except NotFound:
            raise HTTPException(404, "Mission not found.") from None
        except Conflict as error:
            raise HTTPException(409, str(error)) from None

    @application.get("/api/missions/{identifier}/report")
    def report(identifier: str, x_session_token: Annotated[str, Header()]):
        validate_token(x_session_token)
        run = owned(identifier, x_session_token)
        if run["result"] is None:
            raise HTTPException(409, "Mission has no completed numerical result.")
        payload = {
            "mission_id": identifier,
            "status": run["status"],
            "result": run["result"],
            "events": journal.events(identifier),
        }
        return Response(
            json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="orbit-sentinel-report.json"'},
        )

    return application


app = create_app()
