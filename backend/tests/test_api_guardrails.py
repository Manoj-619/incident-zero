import pytest
from fastapi.testclient import TestClient
from app.config import get_settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(app, headers={"X-Session-Token": "a" * 36}) as c:
        yield c
    get_settings.cache_clear()


def test_live_blocked_without_gemini(client):
    assert client.post("/api/investigations", json={"mode": "live"}).status_code == 503


def test_replay_isolated_and_approval_idempotent(client):
    a = client.post("/api/investigations", json={"mode": "replay"}).json()
    b = client.post("/api/investigations", json={"mode": "replay"}).json()
    assert a["replay"] and a["investigation_id"] != b["investigation_id"]
    path = "/api/investigations/" + a["investigation_id"]
    assert client.get(path, headers={"X-Session-Token": "b" * 36}).status_code == 404
    body = {"investigation_id": a["investigation_id"], "approved": True}
    assert (
        client.post(
            "/api/remediation/approve", json=body, headers={"X-Session-Token": "b" * 36}
        ).status_code
        == 404
    )
    missing = dict(body)
    missing.pop("approved")
    assert client.post("/api/remediation/approve", json=missing).status_code == 422
    first = client.post("/api/remediation/approve", json=body).json()
    second = client.post("/api/remediation/approve", json=body).json()
    assert first == second
    assert first["remediation"]["recovery"]["checkout_p99_after_ms"] < 2140
    assert (
        client.get("/api/investigations/" + b["investigation_id"]).json()[
            "remediation"
        ]["executed"]
        is False
    )


def test_inputs_and_missing_session(client):
    assert client.post("/api/investigations", json={"mode": "oops"}).status_code == 422
    assert (
        client.post(
            "/api/investigations", json={"scenario_id": "../tests/ground_truth"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/investigations", json={}, headers={"X-Session-Token": ""}
        ).status_code
        == 401
    )
