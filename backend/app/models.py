from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InvestigationPhase(str, Enum):
    INIT = "init"
    INVESTIGATE = "investigate"
    SKEPTIC = "skeptic"
    EXPERIMENT = "experiment"
    JUDGE = "judge"
    COMPLETE = "complete"
    BUDGET_EXCEEDED = "budget_exceeded"


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    evidence_id: str


class HypothesisScore(BaseModel):
    hypothesis: str
    prior_confidence: float = Field(ge=0, le=1)
    posterior_confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class ExperimentResult(BaseModel):
    experiment_id: str
    hypothesis_tested: str
    code_hash: str
    stdout: str
    stderr: str
    exit_code: int
    summary: str
    supports_hypothesis: bool | None = None


class Verdict(BaseModel):
    leading_hypothesis: str
    confidence: float
    explanation: str
    evidence_ids: list[str]
    experiment_ids: list[str]


class RemediationPlan(BaseModel):
    action: str
    simulated: bool = True
    approved: bool = False
    executed: bool = False


class BudgetSnapshot(BaseModel):
    llm_rounds: int
    tool_calls: int
    elapsed_seconds: float
    exceeded: bool = False
    reason: str | None = None


class InvestigationState(BaseModel):
    investigation_id: str
    scenario_id: str
    phase: InvestigationPhase
    replay: bool = False
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    hypotheses: list[HypothesisScore] = Field(default_factory=list)
    experiments: list[ExperimentResult] = Field(default_factory=list)
    verdict: Verdict | None = None
    remediation: RemediationPlan | None = None
    budget: BudgetSnapshot
    events: list[dict[str, Any]] = Field(default_factory=list)


class StartInvestigationRequest(BaseModel):
    scenario_id: str = "checkout-p99-spike"
    mode: str = "live"  # live | replay


class ApproveRemediationRequest(BaseModel):
    investigation_id: str
    approved: bool = True
