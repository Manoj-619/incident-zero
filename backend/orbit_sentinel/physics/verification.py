"""Independent RK4 trajectory check and Cartesian probability check.

Shares the physical model and covariance assumption, but not the planner's integration
routine or collision-probability quadrature. This is numerical cross-checking, not flight certification.
"""

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import minimize_scalar

from ..scenarios import Scenario
from .assessment import Encounter
from .dynamics import MU, Array, Trajectory
from .probability import independent_disk_probability, monte_carlo


def rk4_rhs(state: Array) -> Array:
    radius = np.sqrt(np.sum(state[:3] ** 2))
    return np.r_[state[3:], -MU * state[:3] / radius**3]


def independent_path(
    initial: Array,
    horizon: float,
    burn_time: float | None = None,
    dv_eci: Array | None = None,
    step: float = 2.0,
):
    time = 0.0
    state = initial.copy()
    times, positions = [time], [state[:3].copy()]
    burned = False
    while time < horizon:
        if burn_time is not None and not burned and abs(time - burn_time) < 1e-8:
            state[3:] += dv_eci
            burned = True
        target = min(time + step, horizon)
        if burn_time is not None and not burned and time < burn_time < target:
            target = burn_time
        h = target - time
        k1 = rk4_rhs(state)
        k2 = rk4_rhs(state + h * k1 / 2)
        k3 = rk4_rhs(state + h * k2 / 2)
        k4 = rk4_rhs(state + h * k3)
        state += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        time = target
        times.append(time)
        positions.append(state[:3].copy())
    return np.array(times), np.array(positions)


def verify(
    scenario: Scenario,
    trajectory: Trajectory,
    encounters: list[Encounter],
    threshold: float,
    budget_ms: float,
    seed: int,
) -> dict:
    times, positions = independent_path(
        scenario.primary.state, scenario.horizon_s, trajectory.burn_time, trajectory.dv_eci
    )
    reference = np.array([trajectory.state(t)[:3] for t in times])
    max_error_m = float(np.max(np.linalg.norm(positions - reference, axis=1)) * 1000)
    primary_spline = CubicSpline(times, positions)
    rows = []
    for obj in scenario.debris:
        other_times, other_positions = independent_path(obj.state, scenario.horizon_s)
        secondary_spline = CubicSpline(other_times, other_positions)

        def distance_squared(time, secondary_spline=secondary_spline):
            relative = primary_spline(time) - secondary_spline(time)
            return float(relative @ relative)

        coarse = np.linspace(0, scenario.horizon_s, 301)
        distances = np.array([distance_squared(t) for t in coarse])
        possible = [
            (float(coarse[0]), float(distances[0])),
            (float(coarse[-1]), float(distances[-1])),
        ]
        for i in range(1, len(coarse) - 1):
            if distances[i] <= min(distances[i - 1], distances[i + 1]):
                result = minimize_scalar(
                    distance_squared,
                    bounds=(coarse[i - 1], coarse[i + 1]),
                    method="bounded",
                    options={"xatol": 1e-7},
                )
                possible.append((float(result.x), float(result.fun)))
        tca, squared = min(possible, key=lambda result: result[1])
        event = next(event for event in encounters if event.object_id == obj.id)
        independent_pc = independent_disk_probability(
            event.mean_km, event.covariance_km2, event.radius_km
        )
        stress_probabilities = [
            independent_disk_probability(
                event.mean_km, event.covariance_km2 * s["sigma_scale"] ** 2, event.radius_km
            )
            for s in event.stresses
        ]
        difference = abs(independent_pc - event.probability)
        miss_error_m = abs(np.sqrt(squared) - event.miss_km) * 1000
        rows.append(
            {
                "object_id": obj.id,
                "rk4_tca_s": tca,
                "rk4_miss_distance_m": float(np.sqrt(squared) * 1000),
                "miss_agreement_m": float(miss_error_m),
                "independent_probability": independent_pc,
                "probability_absolute_error": difference,
                "worst_stress_probability": max(stress_probabilities),
                "passed": difference <= max(1e-10, event.probability * 1e-4)
                and miss_error_m < 0.5
                and max(stress_probabilities) <= threshold,
            }
        )
    cost = 0.0 if trajectory.dv_rtn_ms is None else float(np.linalg.norm(trajectory.dv_rtn_ms))
    worst = max(encounters, key=lambda event: event.probability)
    passed = max_error_m < 0.5 and cost <= budget_ms + 1e-9 and all(row["passed"] for row in rows)
    return {
        "passed": passed,
        "integrator": "Independent fixed-step RK4 / 2 seconds",
        "probability_method": "Cartesian conditional-normal adaptive quadrature",
        "max_trajectory_disagreement_m": max_error_m,
        "checks": rows,
        "monte_carlo": monte_carlo(worst.mean_km, worst.covariance_km2, worst.radius_km, seed),
        "limitations": "Same two-body dynamics and linearized covariance assumption; no independent physical truth.",
    }
