export type InvestigationPhase =
  | "init"
  | "investigate"
  | "skeptic"
  | "experiment"
  | "judge"
  | "complete"
  | "failed"
  | "budget_exceeded";

export interface ToolCallRecord {
  tool_name: string;
  arguments: Record<string, unknown>;
  output: Record<string, unknown>;
  evidence_id: string;
}

export interface HypothesisScore {
  hypothesis: string;
  prior_confidence: number;
  posterior_confidence: number;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  rationale: string;
}

export interface ExperimentResult {
  experiment_id: string;
  hypothesis_tested: string;
  code_hash: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  summary: string;
  supports_hypothesis: boolean | null;
}

export interface Verdict {
  leading_hypothesis: string;
  confidence: number;
  explanation: string;
  evidence_ids: string[];
  experiment_ids: string[];
}

export interface RemediationPlan {
  action: string;
  simulated: boolean;
  approved: boolean;
  executed: boolean;
  recovery: Record<string, number>;
}

export interface InvestigationState {
  investigation_id: string;
  scenario_id: string;
  phase: InvestigationPhase;
  replay: boolean;
  tool_calls: ToolCallRecord[];
  hypotheses: HypothesisScore[];
  experiments: ExperimentResult[];
  verdict: Verdict | null;
  remediation: RemediationPlan | null;
  budget: {
    llm_rounds: number;
    tool_calls: number;
    elapsed_seconds: number;
    exceeded: boolean;
    reason: string | null;
  };
  events: { phase: string; message: string }[];
}

export interface ScenarioSummary {
  scenario_id: string;
  title: string;
  public_summary: string;
  alert_text: string;
}
