import numpy as np
import pytest

from orbit_sentinel.agents.workflow import run_mission
from orbit_sentinel.models import MissionRequest, Review, ToolPolicy
from orbit_sentinel.physics.assessment import AssessmentEngine
from orbit_sentinel.physics.dynamics import Trajectory
from orbit_sentinel.physics.verification import verify
from orbit_sentinel.scenarios import make_scenario


@pytest.fixture(scope="module")
def crossing():
    events = []
    result = run_mission(
        MissionRequest(), lambda role, kind, payload: events.append((role, kind, payload))
    )
    return result, events


def test_crossing_search_reduces_risk_and_screens_every_object(crossing):
    result, events = crossing
    assert result["decision"] == "approval_pending"
    assert result["verification"]["passed"]
    assert 0 < result["maneuver"]["delta_v_ms"] <= result["parameters"]["max_delta_v_ms"]
    assert (
        len(result["baseline"])
        == len(result["after"])
        == len(result["verification"]["checks"])
        == 2
    )
    for event in result["after"]:
        assert event["worst_stress_probability"] <= result["parameters"]["risk_threshold"]
    assert result["after"][0]["probability"] < result["baseline"][0]["probability"]
    assert {role for role, _, _ in events} == {
        "tracker",
        "risk_analyst",
        "planner",
        "verifier",
        "mission_control",
    }
    assert any(kind == "search_progress" for _, kind, _ in events)


def test_clear_scenario_preserves_fuel():
    result = run_mission(MissionRequest(scenario="clear"), lambda *args: None)
    assert result["decision"] == "no_burn"
    assert result["maneuver"] is None
    assert result["candidate_search"] == []
    assert result["verification"]["passed"]


def test_insufficient_budget_blocks_approval():
    result = run_mission(MissionRequest(max_delta_v_ms=0.02), lambda *args: None)
    assert result["decision"] == "blocked"
    assert result["maneuver"] is None
    assert not result["verification"]["passed"]


def test_verifier_rejects_wrong_reported_miss_distance():
    scenario = make_scenario("clear")
    nominal = Trajectory(scenario.primary.state, scenario.primary.covariance, 2400)
    encounters = AssessmentEngine(scenario).assess(nominal)
    encounters[0].miss_km += 0.01
    assert not verify(scenario, nominal, encounters, 1e-4, 1, 42)["passed"]


def test_live_provider_policy_affects_search_and_review_is_exposed(monkeypatch):
    class Advisor:
        model = "mock-provider"

        def policy(self, evidence):
            assert evidence["baseline"]
            return ToolPolicy(
                axes=["tangential"], burn_fractions=[0.2], rationale="Mock bounded choice"
            )

        def review(self, evidence):
            assert evidence["verification"]["passed"]
            return Review(
                summary="Mock evidence review", caveats=["Synthetic"], evidence_ids=["verification"]
            )

        def close(self):
            pass

    monkeypatch.setattr("orbit_sentinel.agents.workflow.GeminiAdvisor", Advisor)
    result = run_mission(MissionRequest(mode="gemini"), lambda *args: None)
    assert result["mode"] == "gemini"
    assert result["policy"]["axes"] == ["tangential"]
    assert result["ai_review"]["evidence_ids"] == ["verification"]
    assert all(
        np.allclose(np.array(candidate["dv_rtn_ms"])[[0, 2]], 0)
        for candidate in result["candidate_search"]
    )


def test_invalid_provider_policies_rejected():
    with pytest.raises(ValueError):
        ToolPolicy(axes=["radial", "radial"], burn_fractions=[0.2], rationale="")
    with pytest.raises(ValueError):
        ToolPolicy(axes=["radial"], burn_fractions=[2.0], rationale="")
    with pytest.raises(ValueError):
        MissionRequest(max_delta_v_ms=float("nan"))
