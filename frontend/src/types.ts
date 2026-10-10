export type ScenarioId = "crossing" | "uncertain" | "clear";
export type Decision = "approval_pending" | "approved" | "no_burn" | "blocked";
export interface Encounter {
  object_id: string;
  tca_s: number;
  miss_distance_m: number;
  relative_speed_kms: number;
  probability: number;
  mean_plane_m: number[];
  covariance_plane_m2: number[][];
  ellipse_3sigma_m: number[];
  ellipse_rotation_rad: number;
  hard_body_radius_m: number;
  stress_tests: { sigma_scale: number; probability: number }[];
  worst_stress_probability: number;
}
export interface Path {
  times_s: number[];
  positions_km: number[][];
}
export interface OrbitObject extends Path {
  id: string;
  name: string;
  kind: string;
}
export interface Event {
  sequence: number;
  created?: number;
  role: string;
  kind: string;
  payload: Record<string, unknown>;
}
export interface Verification {
  passed: boolean;
  integrator: string;
  probability_method: string;
  max_trajectory_disagreement_m: number;
  checks: {
    object_id: string;
    rk4_tca_s: number;
    rk4_miss_distance_m: number;
    miss_agreement_m: number;
    independent_probability: number;
    probability_absolute_error: number;
    worst_stress_probability: number;
    passed: boolean;
  }[];
  monte_carlo: {
    samples: number;
    hits: number;
    estimate: number;
    wilson_95: number[];
    note: string;
  };
  limitations: string;
}
export interface Result {
  schema_version: number;
  scenario: ScenarioId;
  title: string;
  mode: string;
  source: string;
  parameters: {
    scenario: ScenarioId;
    mode: string;
    max_delta_v_ms: number;
    risk_threshold: number;
    seed: number;
  };
  horizon_s: number;
  decision: Decision;
  baseline: Encounter[];
  after: Encounter[];
  maneuver: null | {
    burn_time_s: number;
    dv_rtn_ms: number[];
    delta_v_ms: number;
    worst_stress_probability: number;
    encounters: Encounter[];
  };
  candidate_search: {
    burn_time_s: number;
    delta_v_ms: number;
    dv_rtn_ms: number[];
    worst_probability: number;
    feasible: boolean;
  }[];
  verification: Verification;
  objects: OrbitObject[];
  after_trajectory: Path;
  policy: { axes: string[]; burn_fractions: number[]; rationale: string };
  energy_relative_drift: number;
  duration_s: number;
  assumptions: string[];
  ai_review?: { summary: string; caveats: string[]; evidence_ids: string[] };
}
export interface Recording {
  result: Result;
  events: Event[];
}
