from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def test_live_blocked_without_gemini(monkeypatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "")
    client2 = TestClient(app)
    res = client2.post(
        "/api/investigations",
        json={"scenario_id": "checkout-p99-spike", "mode": "live"},
    )
    assert res.status_code == 503


def test_replay_always_available() -> None:
    res = client.post(
        "/api/investigations",
        json={"scenario_id": "checkout-p99-spike", "mode": "replay"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["replay"] is True
