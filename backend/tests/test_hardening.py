from concurrent.futures import ThreadPoolExecutor
import pytest
from app.store import Store
from app.evidence import validate_citations
from app.models import Verdict
from app.scenarios import get_scenario
from app.tools.registry import run_tool
from app.sandbox.runner import simulate
from app.orchestrator import run_live_investigation
from app.config import Settings
from app.llm.gemini_client import GeminiClient


def test_atomic_global_quota(tmp_path):
    store = Store(str(tmp_path / "quota.db"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.allow("global", 5, 86400), range(30)))
    assert sum(results) == 5
    assert not Store(store.path).allow("global", 5, 86400)


def test_invalid_citations_rejected():
    with pytest.raises(ValueError):
        validate_citations(["invented"], {"known"})
    with pytest.raises(ValueError):
        validate_citations([], {"known"}, require=True)
    with pytest.raises(ValueError):
        Verdict(
            leading_hypothesis="x",
            confidence=2,
            explanation="x",
            evidence_ids=[],
            experiment_ids=[],
        )


@pytest.mark.parametrize(
    "args",
    [
        {"limit": -1},
        {"limit": 1000},
        {"limit": True},
        {"limit": "5"},
        {"path": "../tests/ground_truth.json"},
    ],
)
def test_tool_validation(args):
    with pytest.raises(ValueError):
        run_tool(get_scenario("checkout-p99-spike"), "fetch_logs", args)


def test_runtime_fixture_has_no_answer_key():
    scenario = get_scenario("checkout-p99-spike")
    assert "ground_truth" not in scenario.model_dump_json()
    assert not hasattr(scenario, "initial_hypothesis_hint")


def test_counterfactual_math():
    pool = simulate("increase_pool")
    lock = simulate("shorten_lock_window")
    assert pool["checkout_p99_after_ms"] == 2138
    assert lock["checkout_p99_after_ms"] == 775
    with pytest.raises(ValueError):
        simulate("shell")


def test_provider_failure_never_substitutes_verdict(monkeypatch):
    monkeypatch.setattr(
        GeminiClient,
        "generate_json",
        lambda *a: (_ for _ in ()).throw(RuntimeError("secret")),
    )
    state = run_live_investigation(
        Settings(gemini_api_key="fake"), "checkout-p99-spike"
    )
    assert state.phase.value == "failed"
    assert state.verdict is None and state.remediation is None
    assert "secret" not in state.model_dump_json()


def test_live_workflow_with_mock_provider(monkeypatch):
    def respond(self, system, user):
        import json

        payload = json.loads(user)
        if "Select tools" in system:
            return {"tool_plan": [{"name": "fetch_metrics", "arguments": {}}]}
        ids = [r["evidence_id"] for r in payload.get("evidence", [])]
        score = {
            "hypothesis": "DB lock waits",
            "prior_confidence": 0.5,
            "posterior_confidence": 0.7,
            "supporting_evidence_ids": ids,
            "contradicting_evidence_ids": [],
            "rationale": "Lock wait exceeds pool wait",
        }
        if "collected evidence" in system:
            return score
        if "Skeptic" in system:
            return {
                "primary": score,
                "alternative": dict(
                    score, hypothesis="Redis pool waits", posterior_confidence=0.2
                ),
            }
        if "Experimenter" in system:
            return {"intervention_id": "shorten_lock_window"}
        return {
            "leading_hypothesis": "DB lock waits",
            "confidence": 0.7,
            "explanation": "Model assumption supported by telemetry",
            "evidence_ids": ids,
            "experiment_ids": [payload["experiment"]["experiment_id"]],
        }

    monkeypatch.setattr(GeminiClient, "generate_json", respond)
    state = run_live_investigation(
        Settings(gemini_api_key="fake"), "checkout-p99-spike"
    )
    assert state.phase.value == "complete"
    assert state.budget.llm_rounds == 5 and state.budget.tool_calls == 2
    assert state.remediation.intervention_id == "shorten_lock_window"
    assert not state.remediation.executed


def test_provider_json_configuration(monkeypatch):
    from types import SimpleNamespace
    from app.llm import gemini_client

    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.models = self

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text='{"ok":true}')

        def close(self):
            pass

    monkeypatch.setattr(gemini_client.genai, "Client", FakeClient)
    client = GeminiClient(Settings(gemini_api_key="test-key"))
    assert client.generate_json("role", "{}") == {"ok": True}
    assert calls[0]["http_options"].timeout == 20000
    assert calls[0]["http_options"].retry_options.attempts == 1
    assert calls[1]["config"].max_output_tokens == 2048
    assert calls[1]["config"].response_mime_type == "application/json"
    client.close()


def test_wall_and_call_caps():
    from app.budget import BudgetTracker, BudgetExceeded

    budget = BudgetTracker(Settings(max_llm_rounds=1, max_tool_calls=1))
    budget.inc_llm()
    with pytest.raises(BudgetExceeded):
        budget.inc_llm()
    budget.reserve_tool()
    with pytest.raises(BudgetExceeded):
        budget.reserve_tool()
    assert budget.llm_rounds == budget.tool_calls == 1
    budget._start -= 1000
    with pytest.raises(BudgetExceeded):
        budget.check_wall()


def test_judge_rejects_invented_citations(monkeypatch):
    from app.agents.judge import run_judge
    from app.budget import BudgetTracker
    from app.models import HypothesisScore, ExperimentResult

    score = HypothesisScore(
        hypothesis="x", prior_confidence=0.5, posterior_confidence=0.5
    )
    experiment = ExperimentResult(
        experiment_id="known",
        hypothesis_tested="x",
        code_hash="x",
        stdout="{}",
        stderr="",
        exit_code=0,
        summary="simulation",
    )
    monkeypatch.setattr(
        GeminiClient,
        "generate_json",
        lambda *a: {
            "leading_hypothesis": "x",
            "confidence": 0.9,
            "explanation": "x",
            "evidence_ids": ["invented"],
            "experiment_ids": ["known"],
        },
    )
    with pytest.raises(ValueError):
        run_judge(
            score,
            score,
            [],
            experiment,
            GeminiClient(Settings(gemini_api_key="fake")),
            BudgetTracker(Settings()),
        )
