"""Auditable role workflow. Every conclusion is backed by exported numerical evidence."""

import time
from collections.abc import Callable

from ..models import MissionRequest
from ..physics.assessment import AssessmentEngine
from ..physics.dynamics import Trajectory, specific_energy
from ..physics.planner import search
from ..physics.verification import verify
from ..scenarios import make_scenario
from .gemini import GeminiAdvisor


class MissionTimeout(RuntimeError):
    pass


def run_mission(request: MissionRequest, emit: Callable[[str, str, dict], None]) -> dict:
    started = time.monotonic()
    advisor = None

    def event(role: str, kind: str, payload: dict):
        if time.monotonic() - started > 120:
            raise MissionTimeout("Mission exceeded the 120-second computation budget.")
        emit(role, kind, payload)

    try:
        scenario = make_scenario(request.scenario)
        engine = AssessmentEngine(scenario)
        nominal = Trajectory(
            scenario.primary.state, scenario.primary.covariance, scenario.horizon_s
        )
        event(
            "tracker",
            "tool_started",
            {"tool": "screen_conjunctions", "objects": len(scenario.debris)},
        )
        baseline = engine.assess(nominal)
        baseline_export = [encounter.export() for encounter in baseline]
        event("tracker", "evidence", {"id": "baseline", "encounters": baseline_export})
        energy = specific_energy(nominal.state(0))
        energy_drift = abs(specific_energy(nominal.state(scenario.horizon_s)) - energy) / abs(
            energy
        )
        event(
            "risk_analyst",
            "tool_started",
            {"tool": "stress_covariance", "sigma_scales": [0.5, 1, 2]},
        )
        baseline_worst = max(
            stress["probability"] for encounter in baseline for stress in encounter.stresses
        )
        safe = baseline_worst <= request.risk_threshold
        event(
            "risk_analyst",
            "evidence",
            {
                "id": "risk",
                "worst_probability": baseline_worst,
                "threshold": request.risk_threshold,
                "action": "no_burn" if safe else "search_maneuvers",
            },
        )
        policy = {
            "axes": ["radial", "tangential", "normal"],
            "burn_fractions": [0.2, 0.45, 0.7],
            "rationale": "Search both signs on every RTN axis at three lead times.",
        }
        if request.mode == "gemini":
            advisor = GeminiAdvisor()
            event(
                "planner",
                "provider_started",
                {"model": advisor.model, "purpose": "bounded tool policy"},
            )
            policy = advisor.policy(
                {
                    "baseline": baseline_export,
                    "risk": {
                        "threshold": request.risk_threshold,
                        "budget_ms": request.max_delta_v_ms,
                    },
                }
            ).model_dump()
            event("planner", "provider_policy", policy)
        selected = None
        evaluated = []
        if not safe:
            event("planner", "tool_started", {"tool": "search_maneuvers", **policy})
            # Includes stress-induced risk even when nominal Pc is below the threshold.
            selected, evaluated = search(
                engine,
                request.max_delta_v_ms,
                request.risk_threshold,
                policy["axes"],
                policy["burn_fractions"],
                lambda data: event("planner", "search_progress", data),
            )
            event(
                "planner",
                "evidence",
                {
                    "id": "maneuver",
                    "evaluations": len(evaluated),
                    "candidate": None if selected is None else selected.export(),
                },
            )
        else:
            event(
                "planner",
                "no_burn",
                {"reason": "Every covariance stress case is below the configured threshold."},
            )
        after_trajectory = nominal if selected is None else selected.trajectory
        after_encounters = baseline if selected is None else selected.encounters
        event(
            "verifier",
            "tool_started",
            {"tool": "verify_candidate", "methods": ["RK4", "Cartesian quadrature"]},
        )
        verification = verify(
            scenario,
            after_trajectory,
            after_encounters,
            request.risk_threshold,
            request.max_delta_v_ms,
            request.seed,
        )
        event("verifier", "evidence", {"id": "verification", **verification})
        decision = (
            "no_burn"
            if safe and verification["passed"]
            else (
                "approval_pending" if selected is not None and verification["passed"] else "blocked"
            )
        )
        objects = [
            {
                "id": scenario.primary.id,
                "name": scenario.primary.name,
                "kind": "satellite",
                **nominal.samples(),
            },
            *[
                {
                    "id": obj.id,
                    "name": obj.name,
                    "kind": "debris",
                    **engine.secondaries[obj.id].samples(),
                }
                for obj in scenario.debris
            ],
        ]
        result = {
            "schema_version": 1,
            "scenario": request.scenario,
            "title": scenario.title,
            "mode": request.mode,
            "source": "synthetic ECI states and synthetic covariance",
            "parameters": request.model_dump(),
            "horizon_s": scenario.horizon_s,
            "decision": decision,
            "baseline": baseline_export,
            "after": [encounter.export() for encounter in after_encounters],
            "maneuver": None if selected is None else selected.export(),
            "candidate_search": evaluated,
            "verification": verification,
            "objects": objects,
            "after_trajectory": after_trajectory.samples(),
            "policy": policy,
            "energy_relative_drift": energy_drift,
            "duration_s": time.monotonic() - started,
            "assumptions": [
                "Earth two-body gravity; no J2, drag, third bodies, or operational catalog",
                "Independent Gaussian state errors; linearized covariance propagation",
                "Short, high-speed encounter approximation; fixed combined hard-body radius",
                "Deterministic inertial impulse; no maneuver execution uncertainty",
                "Finite search over RTN axes; no claim of global optimality",
                "Only listed synthetic objects are screened over a 40-minute horizon",
            ],
        }
        if advisor is not None:
            evidence = {
                "baseline": result["baseline"],
                "risk": {"threshold": request.risk_threshold},
                "maneuver": result["maneuver"],
                "verification": verification,
            }
            result["ai_review"] = advisor.review(evidence).model_dump()
            event("risk_analyst", "provider_review", result["ai_review"])
        event("mission_control", "decision", {"decision": decision, "simulation_only": True})
        return result
    finally:
        if advisor is not None:
            advisor.close()
