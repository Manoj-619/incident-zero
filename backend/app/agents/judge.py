from __future__ import annotations

from app.budget import BudgetTracker
from app.llm.gemini_client import GeminiClient
from app.models import ExperimentResult, HypothesisScore, ToolCallRecord, Verdict

JUDGE_SYSTEM = """You are the Judge in INCIDENT ZERO.
Render a verdict using ONLY hypotheses, skeptic scores, evidence summaries, and experiment stdout.
You do NOT have access to any hidden answer key or ground truth.
Cite evidence_ids and experiment_ids that appear in the input.
Output JSON: {
  "leading_hypothesis": string,
  "confidence": number 0-1,
  "explanation": string,
  "evidence_ids": string[],
  "experiment_ids": string[]
}
"""


def _deterministic_verdict(
    redis_hypothesis: HypothesisScore,
    alt_hypothesis: HypothesisScore,
    records: list[ToolCallRecord],
    experiment: ExperimentResult,
) -> Verdict:
    """Verdict from observable artifacts only — no scenario ground truth."""
    if experiment.supports_hypothesis is False:
        winner = alt_hypothesis
        conf = 0.82
        explanation = (
            "Counterfactual experiment failed to reproduce improvement under the Redis pool theory. "
            "Trace and log evidence point to database lock wait dominating checkout latency."
        )
    elif redis_hypothesis.posterior_confidence > alt_hypothesis.posterior_confidence:
        winner = redis_hypothesis
        conf = winner.posterior_confidence
        explanation = "Evidence weighted toward the leading hypothesis after skeptic review."
    else:
        winner = alt_hypothesis
        conf = winner.posterior_confidence
        explanation = (
            "Skeptic review lowered confidence in the alert-heuristic hypothesis; "
            "DB lock contention better fits metrics, logs, and traces."
        )

    ev_ids = list(
        dict.fromkeys(
            winner.supporting_evidence_ids
            + [r.evidence_id for r in records[:3]]
        )
    )
    return Verdict(
        leading_hypothesis=winner.hypothesis,
        confidence=round(conf, 2),
        explanation=explanation,
        evidence_ids=[e for e in ev_ids if e],
        experiment_ids=[experiment.experiment_id],
    )


def run_judge(
    primary: HypothesisScore,
    alternative: HypothesisScore,
    records: list[ToolCallRecord],
    experiment: ExperimentResult,
    gemini: GeminiClient,
    budget: BudgetTracker,
) -> Verdict:
    budget.check_or_raise()
    verdict = _deterministic_verdict(primary, alternative, records, experiment)

    if gemini.enabled:
        budget.inc_llm()
        budget.check_or_raise()
        # Explicitly exclude ground truth from judge input
        user = {
            "primary_hypothesis": primary.model_dump(),
            "alternative_hypothesis": alternative.model_dump(),
            "evidence": [
                {"evidence_id": r.evidence_id, "tool": r.tool_name, "output": r.output}
                for r in records
            ],
            "experiment": experiment.model_dump(),
        }
        import json

        try:
            parsed = gemini.generate_json(JUDGE_SYSTEM, json.dumps(user, default=str))
            verdict = Verdict(
                leading_hypothesis=str(parsed.get("leading_hypothesis", verdict.leading_hypothesis)),
                confidence=float(parsed.get("confidence", verdict.confidence)),
                explanation=str(parsed.get("explanation", verdict.explanation)),
                evidence_ids=[str(x) for x in parsed.get("evidence_ids", verdict.evidence_ids)],
                experiment_ids=[str(x) for x in parsed.get("experiment_ids", verdict.experiment_ids)],
            )
            valid_ev = {r.evidence_id for r in records}
            verdict.evidence_ids = [e for e in verdict.evidence_ids if e in valid_ev] or verdict.evidence_ids
            if experiment.experiment_id not in verdict.experiment_ids:
                verdict.experiment_ids.append(experiment.experiment_id)
        except Exception:
            pass

    return verdict
