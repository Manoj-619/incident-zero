from __future__ import annotations

import uuid
from typing import Any

from app.agents.investigator import run_investigator
from app.agents.judge import run_judge
from app.agents.skeptic import run_skeptic
from app.budget import BudgetExceeded, BudgetTracker
from app.config import Settings
from app.llm.gemini_client import GeminiClient
from app.models import (
    InvestigationPhase,
    InvestigationState,
    RemediationPlan,
)
from app.replay.loader import load_replay
from app.scenarios import get_scenario


def _event(phase: str, message: str, **extra: Any) -> dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "phase": phase,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def run_live_investigation(settings: Settings, scenario_id: str) -> InvestigationState:
    scenario = get_scenario(scenario_id)
    inv_id = str(uuid.uuid4())
    budget = BudgetTracker(settings)
    gemini = GeminiClient(settings)
    state = InvestigationState(
        investigation_id=inv_id,
        scenario_id=scenario_id,
        phase=InvestigationPhase.INIT,
        replay=False,
        budget=budget.snapshot(),
        events=[_event("init", scenario.public_summary)],
    )

    try:
        state.phase = InvestigationPhase.INVESTIGATE
        state.events.append(
            _event("investigate", "Investigator gathering observability evidence")
        )
        hypothesis, _conf, records, h0 = run_investigator(scenario, gemini, budget)
        state.tool_calls.extend(records)
        state.hypotheses.append(h0)
        state.budget = budget.snapshot()

        state.phase = InvestigationPhase.SKEPTIC
        state.events.append(
            _event("skeptic", "Hypothesis Battle — Skeptic scoring evidence")
        )
        h1, alt = run_skeptic(hypothesis, records, h0, gemini, budget)
        state.hypotheses.extend([h1, alt])
        state.budget = budget.snapshot()

        state.phase = InvestigationPhase.EXPERIMENT
        state.events.append(
            _event("experiment", "Counterfactual Lab — deterministic Python simulation")
        )
        from app.agents.investigator import ask
        from app.sandbox.runner import INTERVENTIONS, simulate
        from app.evidence import new_experiment_id
        from app.models import ExperimentResult
        import json

        selected = ask(
            gemini,
            budget,
            'You are the Experimenter. Select one intervention_id from the allowlist to test the competing hypotheses. Return {"intervention_id": string}.',
            {
                "hypotheses": [h1.model_dump(), alt.model_dump()],
                "allowlist": sorted(INTERVENTIONS),
            },
        )["intervention_id"]
        budget.reserve_tool()
        outcome = simulate(selected, scenario.tool_fixtures["fetch_metrics"])
        eid, digest = new_experiment_id(
            json.dumps({"intervention": selected, "outcome": outcome}, sort_keys=True)
        )
        experiment = ExperimentResult(
            experiment_id=eid,
            hypothesis_tested=h1.hypothesis,
            code_hash=digest,
            stdout=json.dumps(outcome),
            stderr="",
            exit_code=0,
            summary="Simulated additive latency model; assumes unchanged non-intervened waits. Not production evidence.",
        )
        state.experiments.append(experiment)
        state.budget = budget.snapshot()

        state.phase = InvestigationPhase.JUDGE
        state.events.append(
            _event(
                "judge", "Judge rendering verdict from evidence and experiments only"
            )
        )
        verdict = run_judge(h1, alt, records, experiment, gemini, budget)
        state.verdict = verdict
        state.budget = budget.snapshot()

        if (
            verdict.confidence > 0.3
            and verdict.evidence_ids
            and experiment.experiment_id in verdict.experiment_ids
            and outcome["checkout_p99_after_ms"]
            < outcome["checkout_p99_before_ms"] * 0.9
        ):
            state.remediation = RemediationPlan(
                action=f"Apply {selected} in simulation only; verify modeled latency improvement.",
                intervention_id=selected,
            )
        state.phase = InvestigationPhase.COMPLETE
        state.events.append(
            _event("complete", "Investigation complete — remediation awaiting approval")
        )
    except BudgetExceeded as exc:
        state.phase = InvestigationPhase.BUDGET_EXCEEDED
        state.budget = exc.snapshot
        state.events.append(_event("budget", f"Stopped: {exc.snapshot.reason}"))

    except Exception:
        state.phase = InvestigationPhase.FAILED
        state.verdict = None
        state.remediation = None
        state.events.append(
            _event(
                "failed",
                "Provider or evidence validation failed; no diagnosis or remediation substituted. Use replay or retry.",
            )
        )
    finally:
        state.budget = budget.snapshot()
        gemini.close()
    return state


def run_replay_investigation(scenario_id: str) -> InvestigationState:
    return load_replay(scenario_id)
