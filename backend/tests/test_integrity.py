import inspect
import json
from pathlib import Path

import pytest

from app.agents.experimenter import run_experimenter
from app.agents.judge import run_judge
from app.agents.skeptic import _score_from_evidence, run_skeptic
from app.budget import BudgetTracker
from app.config import Settings
from app.evidence import new_evidence_id
from app.llm.gemini_client import GeminiClient
from app.models import HypothesisScore, ToolCallRecord
from app.orchestrator import run_live_investigation, run_replay_investigation
from app.replay.loader import load_replay
from app.scenarios import get_scenario
from app.tools.registry import run_tool


@pytest.fixture
def settings_no_gemini() -> Settings:
    return Settings(gemini_api_key="", allow_public_live=True)


def test_replay_without_api_key(settings_no_gemini: Settings) -> None:
    state = run_replay_investigation("checkout-p99-spike")
    assert state.replay is True
    assert state.verdict is not None
    assert state.budget.llm_rounds == 0


def test_tools_produce_stable_evidence_ids() -> None:
    scenario = get_scenario("checkout-p99-spike")
    a = run_tool(scenario, "fetch_metrics", {})
    b = run_tool(scenario, "fetch_metrics", {})
    assert a.evidence_id == b.evidence_id
    assert a.evidence_id.startswith("ev-")


def test_experimenter_runs_python_subprocess() -> None:
    scenario = get_scenario("checkout-p99-spike")
    exp = run_experimenter(scenario, "Redis connection pool exhaustion")
    assert exp.exit_code == 0
    assert "simulated_checkout_p99_ms" in exp.stdout
    assert exp.supports_hypothesis is False


def test_experimenter_deterministic() -> None:
    scenario = get_scenario("checkout-p99-spike")
    e1 = run_experimenter(scenario, "Redis connection pool exhaustion")
    e2 = run_experimenter(scenario, "Redis connection pool exhaustion")
    assert e1.stdout == e2.stdout
    assert e1.code_hash == e2.code_hash


def test_skeptic_lowers_confidence_when_contradicted() -> None:
    scenario = get_scenario("checkout-p99-spike")
    records = [
        run_tool(scenario, "fetch_metrics", {}),
        run_tool(scenario, "fetch_logs", {"limit": 5}),
        run_tool(scenario, "fetch_traces", {}),
    ]
    prior = HypothesisScore(
        hypothesis="Redis connection pool exhaustion",
        prior_confidence=0.55,
        posterior_confidence=0.55,
    )
    scored = _score_from_evidence("Redis connection pool exhaustion", records, prior)
    assert scored.posterior_confidence < prior.posterior_confidence
    assert scored.contradicting_evidence_ids


def test_skeptic_can_agree_when_supported() -> None:
    scenario = get_scenario("checkout-p99-spike")
    fake_output = {
        "metrics": {
            "redis_pool_wait_ms_p99": 400,
            "db_lock_wait_ms_p99": 10,
        }
    }
    eid = new_evidence_id("fetch_metrics", {}, fake_output)
    rec = ToolCallRecord(
        tool_name="fetch_metrics",
        arguments={},
        output=fake_output,
        evidence_id=eid,
    )
    prior = HypothesisScore(
        hypothesis="Redis connection pool exhaustion",
        prior_confidence=0.4,
        posterior_confidence=0.4,
    )
    scored = _score_from_evidence("Redis connection pool exhaustion", [rec], prior)
    assert scored.posterior_confidence > prior.posterior_confidence
    assert eid in scored.supporting_evidence_ids


def test_judge_module_never_loads_ground_truth() -> None:
    source = inspect.getsource(run_judge)
    assert "ground_truth" not in source
    scenario_path = Path(__file__).resolve().parents[1] / "app" / "agents" / "judge.py"
    assert "ground_truth_internal_only" not in scenario_path.read_text()


def test_verdict_citations_exist_in_tool_outputs() -> None:
    state = load_replay("checkout-p99-spike")
    assert state.verdict
    ev_ids = {t.evidence_id for t in state.tool_calls}
    for eid in state.verdict.evidence_ids:
        assert eid in ev_ids


def test_budget_terminates(settings_no_gemini: Settings) -> None:
    tight = Settings(
        gemini_api_key="",
        max_tool_calls=1,
        max_llm_rounds=0,
        max_wall_seconds=120,
        allow_public_live=True,
    )
    state = run_live_investigation(tight, "checkout-p99-spike")
    assert state.phase.value == "budget_exceeded" or state.budget.tool_calls <= 1


def test_remediation_not_executed_by_default() -> None:
    state = load_replay("checkout-p99-spike")
    assert state.remediation
    assert state.remediation.executed is False
    assert state.remediation.approved is False


def test_scenario_ground_truth_not_in_replay_export() -> None:
    replay_path = Path(__file__).resolve().parents[1] / "app" / "replay" / "checkout_p99_replay.json"
    text = replay_path.read_text()
    assert "ground_truth_internal_only" not in text
