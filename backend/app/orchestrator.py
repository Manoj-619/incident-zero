from __future__ import annotations

import uuid
from typing import Any

from app.agents.experimenter import run_experimenter
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
    Verdict,
)
from app.replay.loader import load_replay
from app.scenarios import get_scenario

ALT_HYPOTHESIS = "PostgreSQL row lock contention on orders during settlement batch"


def _event(phase: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"phase": phase, "message": message, **extra}


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
        state.events.append(_event("investigate", "Investigator gathering observability evidence"))
        hypothesis, _conf, records, h0 = run_investigator(scenario, gemini, budget)
        state.tool_calls.extend(records)
        state.hypotheses.append(h0)
        state.budget = budget.snapshot()

        state.phase = InvestigationPhase.SKEPTIC
        state.events.append(_event("skeptic", "Hypothesis Battle — Skeptic scoring evidence"))
        h1 = run_skeptic(hypothesis, records, h0, gemini, budget)
        state.hypotheses.append(h1)
        state.budget = budget.snapshot()

        alt = h1.model_copy(
            update={
                "hypothesis": ALT_HYPOTHESIS,
                "prior_confidence": h1.posterior_confidence,
                "posterior_confidence": 0.72,
                "rationale": "Alternative driven by lock-wait metrics, slow query logs, and trace share.",
            }
        )
        if h1.contradicting_evidence_ids:
            alt.supporting_evidence_ids = list(
                dict.fromkeys(h1.contradicting_evidence_ids + h1.supporting_evidence_ids)
            )
            alt.contradicting_evidence_ids = []

        state.phase = InvestigationPhase.EXPERIMENT
        state.events.append(_event("experiment", "Counterfactual Lab — deterministic Python simulation"))
        experiment = run_experimenter(scenario, h1.hypothesis)
        state.experiments.append(experiment)
        state.budget = budget.snapshot()

        state.phase = InvestigationPhase.JUDGE
        state.events.append(_event("judge", "Judge rendering verdict from evidence and experiments only"))
        verdict = run_judge(h1, alt, records, experiment, gemini, budget)
        state.verdict = verdict
        state.budget = budget.snapshot()

        state.remediation = RemediationPlan(
            action="Stagger settlement batch + shorten orders row lock window (simulated)",
            simulated=True,
            approved=False,
            executed=False,
        )
        state.phase = InvestigationPhase.COMPLETE
        state.events.append(_event("complete", "Investigation complete — remediation awaiting approval"))
    except BudgetExceeded as exc:
        state.phase = InvestigationPhase.BUDGET_EXCEEDED
        state.budget = exc.snapshot
        state.events.append(_event("budget", f"Stopped: {exc.snapshot.reason}"))

    return state


def run_replay_investigation(scenario_id: str) -> InvestigationState:
    return load_replay(scenario_id)
