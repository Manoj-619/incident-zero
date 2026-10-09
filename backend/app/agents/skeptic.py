from __future__ import annotations

from app.models import HypothesisScore, ToolCallRecord

SKEPTIC_SYSTEM = """You are the Skeptic in INCIDENT ZERO.
Evaluate the hypothesis against ONLY the evidence payloads provided.
You MUST agree when evidence strongly supports the hypothesis.
You MUST lower confidence when evidence contradicts it.
Do NOT disagree by default.
Output JSON: {
  "posterior_confidence": number 0-1,
  "supporting_evidence_ids": string[],
  "contradicting_evidence_ids": string[],
  "rationale": string
}
"""


def _score_from_evidence(
    hypothesis: str,
    records: list[ToolCallRecord],
    prior: HypothesisScore,
) -> HypothesisScore:
    """Deterministic evidence evaluation — same inputs always yield same scores."""
    h = hypothesis.lower()
    supporting = list(prior.supporting_evidence_ids)
    contradicting = list(prior.contradicting_evidence_ids)
    posterior = prior.posterior_confidence

    redis_story = "redis" in h or "pool" in h
    db_story = "lock" in h or "postgres" in h or "database" in h

    for rec in records:
        if rec.tool_name == "fetch_metrics":
            m = rec.output.get("metrics", {})
            pool_wait = float(m.get("redis_pool_wait_ms_p99", 0))
            lock_wait = float(m.get("db_lock_wait_ms_p99", 0))
            if redis_story:
                if pool_wait < 30:
                    if rec.evidence_id not in contradicting:
                        contradicting.append(rec.evidence_id)
                    posterior = min(posterior, 0.25)
                elif pool_wait > 200:
                    supporting.append(rec.evidence_id)
                    posterior = min(1.0, posterior + 0.15)
            if db_story and lock_wait > 800:
                supporting.append(rec.evidence_id)
                posterior = min(1.0, posterior + 0.2)
        if rec.tool_name == "fetch_logs":
            for line in rec.output.get("logs", []):
                msg = str(line.get("msg", "")).lower()
                if "row lock" in msg or "slow query" in msg:
                    if db_story:
                        supporting.append(rec.evidence_id)
                        posterior = min(1.0, posterior + 0.15)
                    if redis_story:
                        contradicting.append(rec.evidence_id)
                        posterior = min(posterior, 0.3)
        if rec.tool_name == "fetch_traces":
            t = rec.output.get("traces", {})
            lock_share = float(t.get("postgres_lock_wait_share_pct", 0))
            redis_share = float(t.get("redis_span_share_pct", 0))
            if redis_story:
                if lock_share > 50:
                    contradicting.append(rec.evidence_id)
                    posterior = min(posterior, 0.2)
                if redis_share > 40:
                    supporting.append(rec.evidence_id)
                    posterior = min(1.0, posterior + 0.1)

    supporting = list(dict.fromkeys(supporting))
    contradicting = list(dict.fromkeys(contradicting))

    if supporting and not contradicting:
        posterior = max(posterior, 0.65)
    if contradicting and len(contradicting) >= len(supporting):
        posterior = min(posterior, 0.35)

    rationale_parts = []
    if supporting:
        rationale_parts.append(f"Supporting evidence: {', '.join(supporting)}.")
    if contradicting:
        rationale_parts.append(f"Contradicting evidence: {', '.join(contradicting)}.")
    if not supporting and not contradicting:
        rationale_parts.append("Insufficient evidence to move confidence materially.")

    return HypothesisScore(
        hypothesis=hypothesis,
        prior_confidence=prior.posterior_confidence,
        posterior_confidence=round(max(0.05, min(0.95, posterior)), 2),
        supporting_evidence_ids=supporting,
        contradicting_evidence_ids=contradicting,
        rationale=" ".join(rationale_parts),
    )


def run_skeptic(hypothesis, records, prior, gemini, budget):
    from app.agents.investigator import ask
    from app.evidence import validate_citations

    result = ask(
        gemini,
        budget,
        'You are the Skeptic. Challenge causal assumptions; agree if supported. Return {"primary": HypothesisScore, "alternative": HypothesisScore}. Each HypothesisScore contains hypothesis, prior_confidence, posterior_confidence (heuristic 0-1), supporting_evidence_ids, contradicting_evidence_ids, rationale. The alternative must be inferred from the evidence, never invented as a fact.',
        {"primary": prior.model_dump(), "evidence": [r.model_dump() for r in records]},
    )
    primary = HypothesisScore.model_validate(result["primary"])
    alternative = HypothesisScore.model_validate(result["alternative"])
    valid = {r.evidence_id for r in records}
    for score in (primary, alternative):
        validate_citations(score.supporting_evidence_ids, valid)
        validate_citations(score.contradicting_evidence_ids, valid)
    return primary, alternative
