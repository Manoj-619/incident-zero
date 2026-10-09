from app.agents.investigator import ask
from app.evidence import validate_citations
from app.models import Verdict


def run_judge(primary, alternative, records, experiment, gemini, budget):
    verdict = Verdict.model_validate(
        ask(
            gemini,
            budget,
            "You are the Judge. Compare hypotheses against collected telemetry and simulated experiments. Experiments test assumptions, not real-world causality. Return leading_hypothesis, confidence (heuristic 0-1), explanation, evidence_ids, experiment_ids. Use only supplied IDs. If evidence is weak, state Root cause undetermined — further investigation required with confidence <=0.3.",
            {
                "primary": primary.model_dump(),
                "alternative": alternative.model_dump(),
                "evidence": [r.model_dump() for r in records],
                "experiment": experiment.model_dump(),
            },
        )
    )
    validate_citations(
        verdict.evidence_ids,
        {r.evidence_id for r in records},
        require=verdict.confidence > 0.3,
    )
    validate_citations(verdict.experiment_ids, {experiment.experiment_id})
    return verdict
