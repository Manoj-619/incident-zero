"""Finite maneuver search with full catalog screening and direction-wise refinement."""

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .assessment import AssessmentEngine, Encounter
from .dynamics import Trajectory


@dataclass
class Candidate:
    burn_time_s: float
    dv_rtn_ms: np.ndarray
    encounters: list[Encounter]
    trajectory: Trajectory

    @property
    def cost(self):
        return float(np.linalg.norm(self.dv_rtn_ms))

    @property
    def worst_risk(self):
        return max(stress["probability"] for event in self.encounters for stress in event.stresses)

    def export(self):
        return {
            "burn_time_s": self.burn_time_s,
            "dv_rtn_ms": self.dv_rtn_ms.tolist(),
            "delta_v_ms": self.cost,
            "worst_stress_probability": self.worst_risk,
            "encounters": [event.export() for event in self.encounters],
        }


def search(
    engine: AssessmentEngine,
    budget_ms: float,
    threshold: float,
    axes: list[str],
    burn_fractions: list[float],
    progress: Callable[[dict], None],
) -> tuple[Candidate | None, list[dict]]:
    scenario = engine.scenario
    baseline = engine.assess(
        Trajectory(scenario.primary.state, scenario.primary.covariance, scenario.horizon_s)
    )
    first_tca = min(
        event.time_s
        for event in baseline
        if max(stress["probability"] for stress in event.stresses) >= threshold
    )
    times = sorted(set(max(30.0, first_tca * fraction) for fraction in burn_fractions))
    candidates: list[Candidate] = []
    evaluated = []
    axis_indices = {"radial": 0, "tangential": 1, "normal": 2}
    evaluations = 0

    def evaluate(time: float, vector: np.ndarray) -> Candidate:
        nonlocal evaluations
        trajectory = Trajectory(
            scenario.primary.state,
            scenario.primary.covariance,
            scenario.horizon_s,
            burn_time=time,
            dv_rtn_ms=vector,
        )
        result = Candidate(time, vector.copy(), engine.assess(trajectory), trajectory)
        evaluations += 1
        evaluated.append(
            {
                "burn_time_s": time,
                "delta_v_ms": result.cost,
                "dv_rtn_ms": vector.tolist(),
                "worst_probability": result.worst_risk,
                "feasible": result.worst_risk <= threshold,
            }
        )
        return result

    for time in times:
        for axis in axes:
            for sign in (-1, 1):
                direction = np.eye(3)[axis_indices[axis]] * sign
                previous_magnitude = 0.0
                for fraction in (0.0625, 0.125, 0.25, 0.5, 1.0):
                    magnitude = budget_ms * fraction
                    candidate = evaluate(time, direction * magnitude)
                    if candidate.worst_risk <= threshold:
                        # Refine only the first feasible bracket along this direction, not a global optimum.
                        lower, upper = previous_magnitude, magnitude
                        best = candidate
                        for _ in range(6):
                            middle = (lower + upper) / 2
                            trial = evaluate(time, direction * middle)
                            if trial.worst_risk <= threshold:
                                best, upper = trial, middle
                            else:
                                lower = middle
                        candidates.append(best)
                        break
                    previous_magnitude = magnitude
        progress(
            {
                "burn_time_s": time,
                "evaluations": evaluations,
                "feasible_directions": len(candidates),
            }
        )
    if not candidates:
        return None, evaluated
    selected = min(candidates, key=lambda candidate: (candidate.cost, candidate.worst_risk))
    # Safety margin inside the selected bracket; bounded by the declared fuel budget.
    vector = selected.dv_rtn_ms * min(1.03, budget_ms / selected.cost)
    selected = evaluate(selected.burn_time_s, vector)
    return selected, evaluated
