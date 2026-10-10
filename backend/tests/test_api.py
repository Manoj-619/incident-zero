import time

import pytest
from fastapi.testclient import TestClient

from orbit_sentinel.api import create_app
from orbit_sentinel.store import Conflict, Journal, NotFound

TOKEN = "a" * 64
OTHER = "b" * 64


@pytest.fixture
def client(tmp_path):
    application = create_app(str(tmp_path / "test.sqlite3"))
    with TestClient(application) as client:
        yield client


def test_health_and_strict_input(client):
    assert client.get("/api/health").json()["simulation_only"]
    assert len(client.get("/api/scenarios").json()) == 3
    headers = {"X-Session-Token": TOKEN}
    assert (
        client.post("/api/missions", headers=headers, json={"scenario": "invented"}).status_code
        == 422
    )
    assert (
        client.post("/api/missions", headers=headers, json={"extra": "injection"}).status_code
        == 422
    )
    assert (
        client.post("/api/missions", headers={"X-Session-Token": "short"}, json={}).status_code
        == 400
    )


def test_missing_provider_configuration_is_not_silently_replayed(client, monkeypatch):
    monkeypatch.delenv("OPERATOR_SECRET", raising=False)
    response = client.post(
        "/api/missions", headers={"X-Session-Token": TOKEN}, json={"mode": "gemini"}
    )
    assert response.status_code == 403


def test_api_replay_no_burn_ownership_report_and_sse(client):
    headers = {"X-Session-Token": TOKEN}
    response = client.post("/api/missions", headers=headers, json={"scenario": "clear"})
    assert response.status_code == 202
    identifier = response.json()["id"]
    path = f"/api/missions/{identifier}"
    assert client.get(path, headers={"X-Session-Token": OTHER}).status_code == 404
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = client.get(path, headers=headers).json()
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["status"] == "no_burn"
    report = client.get(path + "/report", headers=headers)
    assert report.status_code == 200 and report.json()["result"]["verification"]["passed"]
    assert client.post(path + "/approve", headers=headers).status_code == 409
    assert client.get(path + "/events", headers=headers).text.count("event: mission") >= 8
    assert client.get(path + "/events", headers={"X-Session-Token": OTHER}).status_code == 404


def test_approval_is_atomic_idempotent_and_owned(tmp_path):
    journal = Journal(str(tmp_path / "journal.sqlite3"))
    identifier = journal.create(TOKEN, {})
    journal.finish(
        identifier, result={"decision": "approval_pending", "verification": {"passed": True}}
    )
    with pytest.raises(NotFound):
        journal.approve(identifier, OTHER)
    assert journal.approve(identifier, TOKEN)["already_approved"] is False
    assert journal.approve(identifier, TOKEN)["already_approved"] is True
    assert len(journal.events(identifier)) == 1
    blocked = journal.create(TOKEN, {})
    journal.finish(blocked, result={"decision": "blocked", "verification": {"passed": False}})
    with pytest.raises(Conflict):
        journal.approve(blocked, TOKEN)


def test_quota_and_restart_recovery(tmp_path):
    journal = Journal(str(tmp_path / "journal.sqlite3"))
    identifiers = [journal.create(TOKEN, {}) for _ in range(12)]
    with pytest.raises(Conflict):
        journal.create(TOKEN, {})
    journal.recover()
    assert all(journal.get(identifier, TOKEN)["status"] == "failed" for identifier in identifiers)
