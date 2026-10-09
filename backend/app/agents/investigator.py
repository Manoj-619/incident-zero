from __future__ import annotations

from typing import Any

from app.budget import BudgetTracker
from app.llm.gemini_client import GeminiClient
from app.models import HypothesisScore, ToolCallRecord
from app.scenarios import Scenario
from app.tools.registry import TOOL_SCHEMAS, run_tool

INVESTIGATOR_SYSTEM = """You are the Investigator for INCIDENT ZERO.
Use ONLY the listed observability tools to gather evidence.
Propose one leading hypothesis based on alert text, then refine after tools run.
Never invent metric values — only cite evidence_id values from tool results you receive.
Output JSON: {
  "leading_hypothesis": string,
  "confidence": number 0-1,
  "tool_plan": [{"name": string, "arguments": object}]
}
"""


def _default_tool_plan() -> list[dict[str, Any]]:
    return [
        {"name": "fetch_metrics", "arguments": {}},
        {"name": "fetch_logs", "arguments": {"limit": 10}},
        {"name": "fetch_traces", "arguments": {}},
    ]


def run_investigator(
    scenario: Scenario,
    gemini: GeminiClient,
    budget: BudgetTracker,
) -> tuple[str, float, list[ToolCallRecord], HypothesisScore]:
    budget.check_or_raise()
    tool_plan = _default_tool_plan()
    hypothesis = scenario.initial_hypothesis_hint
    confidence = 0.55

    if gemini.enabled:
        budget.inc_llm()
        budget.check_or_raise()
        user = (
            f"Alert: {scenario.alert_text}\n"
            f"Summary: {scenario.public_summary}\n"
            f"Available tools: {TOOL_SCHEMAS}\n"
            "Plan tool calls and initial hypothesis."
        )
        try:
            parsed = gemini.generate_json(INVESTIGATOR_SYSTEM, user)
            hypothesis = str(parsed.get("leading_hypothesis", hypothesis))
            confidence = float(parsed.get("confidence", confidence))
            plan = parsed.get("tool_plan")
            if isinstance(plan, list) and plan:
                tool_plan = plan
        except Exception:
            pass

    records: list[ToolCallRecord] = []
    for step in tool_plan:
        budget.check_or_raise()
        name = str(step.get("name", ""))
        args = step.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        budget.inc_tool()
        rec = run_tool(scenario, name, args)
        records.append(rec)

    supporting: list[str] = []
    contradicting: list[str] = []
    h_lower = hypothesis.lower()
    redis_story = "redis" in h_lower or "pool" in h_lower

    for rec in records:
        if rec.tool_name == "fetch_metrics":
            m = rec.output.get("metrics", {})
            if redis_story:
                if m.get("redis_pool_wait_ms_p99", 99) < 50:
                    contradicting.append(rec.evidence_id)
                if m.get("db_lock_wait_ms_p99", 0) > 500:
                    contradicting.append(rec.evidence_id)
            else:
                if m.get("db_lock_wait_ms_p99", 0) > 500:
                    supporting.append(rec.evidence_id)
        if rec.tool_name == "fetch_traces":
            t = rec.output.get("traces", {})
            if redis_story:
                if t.get("postgres_lock_wait_share_pct", 0) > 50:
                    contradicting.append(rec.evidence_id)
                if t.get("redis_span_share_pct", 100) < 10:
                    contradicting.append(rec.evidence_id)
            elif t.get("postgres_lock_wait_share_pct", 0) > 50:
                supporting.append(rec.evidence_id)

    # Adjust confidence from evidence (Investigator is not omniscient — data moves belief)
    if contradicting:
        confidence = min(confidence, 0.45)
    if supporting and not contradicting:
        confidence = max(confidence, 0.7)

    score = HypothesisScore(
        hypothesis=hypothesis,
        prior_confidence=0.55,
        posterior_confidence=round(confidence, 2),
        supporting_evidence_ids=list(dict.fromkeys(supporting)),
        contradicting_evidence_ids=list(dict.fromkeys(contradicting)),
        rationale="Initial read from alert; updated after observability tool outputs.",
    )
    return hypothesis, confidence, records, score
