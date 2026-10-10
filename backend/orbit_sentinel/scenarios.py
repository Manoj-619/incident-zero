"""Reproducible synthetic ECI scenarios. No live catalog or operational CDMs."""

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from .physics.dynamics import MU, Array, Trajectory, derivative, rtn_frame


@dataclass(frozen=True)
class Object:
    id: str
    name: str
    state: Array
    covariance: Array
    radius_km: float


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    description: str
    primary: Object
    debris: tuple[Object, ...]
    horizon_s: float = 2400


def initial_from_encounter(state: Array, time: float) -> Array:
    result = solve_ivp(derivative, (time, 0), state, method="DOP853", rtol=2e-12, atol=1e-12)
    if not result.success:
        raise RuntimeError("Scenario construction failed.")
    return result.y[:, -1]


def make_scenario(kind: str) -> Scenario:
    if kind not in {"crossing", "uncertain", "clear"}:
        raise ValueError("Unknown scenario.")
    speed = np.sqrt(MU / 7000)
    primary_tca = np.array([7000.0, 0, 0, 0, speed * np.cos(0.6), speed * np.sin(0.6)])
    primary_cov = np.diag([0.025**2] * 3 + [0.000015**2] * 3)
    primary = Object(
        "sentinel-01", "SENTINEL / 01", initial_from_encounter(primary_tca, 900), primary_cov, 0.008
    )
    offset = {"crossing": 0.035, "uncertain": 0.15, "clear": 2.5}[kind]
    secondary_tca = np.array(
        [7000 + offset, 0.005, 0.015, 0, speed * np.cos(-0.5), speed * np.sin(-0.5)]
    )
    sigma = 0.12 if kind == "uncertain" else 0.04
    secondary_cov = np.diag([sigma**2] * 3 + [0.00002**2] * 3)
    debris_one = Object(
        "debris-17", "DEBRIS / 17", initial_from_encounter(secondary_tca, 900), secondary_cov, 0.004
    )
    nominal = Trajectory(primary.state, primary.covariance, 2400)
    state_two = nominal.state(1850).copy()
    state_two[:3] += np.array([2.8, -1.5, 0.8])
    frame = rtn_frame(state_two)
    state_two[3:] = speed * (np.cos(1.4) * frame[:, 1] + np.sin(1.4) * frame[:, 2])
    debris_two = Object(
        "debris-42", "DEBRIS / 42", initial_from_encounter(state_two, 1850), secondary_cov, 0.003
    )
    descriptions = {
        "crossing": (
            "CROSSING PATHS",
            "A high-speed crossing encounter at T+15 minutes. A second object tests follow-on screening.",
        ),
        "uncertain": (
            "UNCERTAINTY TRAP",
            "A wider nominal miss with inflated synthetic covariance. Stress testing may reverse intuition.",
        ),
        "clear": (
            "QUIET ORBIT",
            "A benign conjunction. The correct response is to avoid an unnecessary burn.",
        ),
    }
    title, description = descriptions[kind]
    return Scenario(kind, title, description, primary, (debris_one, debris_two))


def catalog() -> list[dict]:
    return [
        {
            "id": kind,
            "title": make_scenario(kind).title,
            "description": make_scenario(kind).description,
        }
        for kind in ("crossing", "uncertain", "clear")
    ]
