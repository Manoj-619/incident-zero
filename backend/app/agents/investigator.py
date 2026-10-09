from __future__ import annotations
import json
from pydantic import BaseModel, ConfigDict, Field
from app.budget import BudgetTracker
from app.evidence import validate_citations
from app.llm.gemini_client import GeminiClient
from app.models import HypothesisScore, ToolCallRecord
from app.scenarios import Scenario
from app.tools.registry import TOOL_SCHEMAS, run_tool


class ToolStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolPlan(BaseModel):
    tool_plan: list[ToolStep] = Field(min_length=1, max_length=6)


def ask(gemini, budget, system, payload):
    budget.check_wall()
    budget.inc_llm()
    result = gemini.generate_json(system, json.dumps(payload))
    budget.check_wall()
    return result


def run_investigator(scenario: Scenario, gemini: GeminiClient, budget: BudgetTracker):
    plan = ToolPlan.model_validate(
        ask(
            gemini,
            budget,
            'You are the Investigator. Select tools to investigate the alert. Return {"tool_plan":[{"name":string,"arguments":object}]}.',
            {"alert": scenario.alert_text, "tools": TOOL_SCHEMAS},
        )
    )
    records: list[ToolCallRecord] = []
    for step in plan.tool_plan:
        budget.reserve_tool()
        records.append(run_tool(scenario, step.name, step.arguments))
    score = HypothesisScore.model_validate(
        ask(
            gemini,
            budget,
            "Evaluate the collected evidence. Return hypothesis, prior_confidence, posterior_confidence (heuristic 0-1), supporting_evidence_ids, contradicting_evidence_ids, rationale. If weak, say root cause undetermined.",
            {"evidence": [r.model_dump() for r in records]},
        )
    )
    valid = {r.evidence_id for r in records}
    validate_citations(score.supporting_evidence_ids, valid)
    validate_citations(score.contradicting_evidence_ids, valid)
    return score.hypothesis, score.posterior_confidence, records, score
