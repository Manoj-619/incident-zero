"""Two-body propagation with variational equations and impulsive maneuvers."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar

MU = 398600.4418  # Earth standard gravitational parameter, km^3/s^2
EARTH_RADIUS = 6378.137
Array = NDArray[np.float64]


def acceleration(position: Array) -> Array:
    radius = np.linalg.norm(position)
    if radius < EARTH_RADIUS:
        raise ValueError("Trajectory intersects Earth; this model does not simulate reentry.")
    return -MU * position / radius**3


def derivative(_time: float, state: Array) -> Array:
    return np.concatenate((state[3:6], acceleration(state[:3])))


def variational_derivative(time: float, augmented: Array) -> Array:
    position = augmented[:3]
    radius = np.linalg.norm(position)
    jacobian = MU * (3 * np.outer(position, position) / radius**5 - np.eye(3) / radius**3)
    system = np.zeros((6, 6))
    system[:3, 3:] = np.eye(3)
    system[3:, :3] = jacobian
    phi = augmented[6:].reshape(6, 6)
    return np.concatenate((derivative(time, augmented[:6]), (system @ phi).ravel()))


def integrate(state: Array, start: float, stop: float, phi: Array | None = None):
    augmented = np.concatenate((state, (np.eye(6) if phi is None else phi).ravel()))
    result = solve_ivp(
        variational_derivative,
        (start, stop),
        augmented,
        method="DOP853",
        rtol=2e-11,
        atol=1e-12,
        dense_output=True,
        max_step=90,
    )
    if not result.success:
        raise RuntimeError("Orbital integration failed.")
    return result


def rtn_frame(state: Array) -> Array:
    radial = state[:3] / np.linalg.norm(state[:3])
    normal = np.cross(state[:3], state[3:6])
    normal /= np.linalg.norm(normal)
    tangent = np.cross(normal, radial)
    return np.column_stack((radial, tangent, normal))


@dataclass
class Trajectory:
    initial: Array
    covariance: Array
    horizon: float
    burn_time: float | None = None
    dv_rtn_ms: Array | None = None

    def __post_init__(self):
        self.pre = integrate(self.initial, 0, self.horizon)
        self.post = None
        self.dv_eci = np.zeros(3)
        if self.burn_time is not None:
            if not 0 < self.burn_time < self.horizon:
                raise ValueError("Burn time must lie inside the propagation horizon.")
            if self.dv_rtn_ms is None or not np.all(np.isfinite(self.dv_rtn_ms)):
                raise ValueError("Finite RTN delta-v is required.")
            at_burn = self.pre.sol(self.burn_time)
            state = at_burn[:6].copy()
            self.dv_eci = rtn_frame(state) @ (self.dv_rtn_ms / 1000)
            state[3:] += self.dv_eci
            # Fixed inertial impulse: nominal RTN frame is not recomputed for uncertain samples.
            self.post = integrate(state, self.burn_time, self.horizon, at_burn[6:].reshape(6, 6))

    def augmented(self, time: float) -> Array:
        if not 0 <= time <= self.horizon:
            raise ValueError("Time outside trajectory horizon.")
        use_post = self.post is not None and time >= self.burn_time
        return (self.post if use_post else self.pre).sol(time)

    def state(self, time: float) -> Array:
        return self.augmented(time)[:6]

    def position_covariance(self, time: float) -> Array:
        phi = self.augmented(time)[6:].reshape(6, 6)
        propagated = phi @ self.covariance @ phi.T
        return (propagated[:3, :3] + propagated[:3, :3].T) / 2

    def samples(self, count: int = 181) -> dict:
        times = np.linspace(0, self.horizon, count)
        return {
            "times_s": times.tolist(),
            "positions_km": [self.state(t)[:3].tolist() for t in times],
        }


def closest_approach(primary: Trajectory, secondary: Trajectory) -> tuple[float, float]:
    """Bracket every sampled local minimum; include boundaries and the impulse discontinuity."""
    times = np.linspace(0, primary.horizon, 161)
    if primary.burn_time is not None:
        times = np.unique(np.append(times, primary.burn_time))

    def distance_squared(time: float) -> float:
        delta = primary.state(time)[:3] - secondary.state(time)[:3]
        return float(delta @ delta)

    distances = np.array([distance_squared(t) for t in times])
    candidates = [(float(times[0]), float(distances[0])), (float(times[-1]), float(distances[-1]))]
    if primary.burn_time is not None:
        candidates.append((primary.burn_time, distance_squared(primary.burn_time)))
    for index in range(1, len(times) - 1):
        if distances[index] <= min(distances[index - 1], distances[index + 1]):
            result = minimize_scalar(
                distance_squared,
                bounds=(times[index - 1], times[index + 1]),
                method="bounded",
                options={"xatol": 1e-7},
            )
            candidates.append((float(result.x), float(result.fun)))
    time, squared = min(candidates, key=lambda item: item[1])
    return time, float(np.sqrt(max(0, squared)))


def specific_energy(state: Array) -> float:
    return float(state[3:] @ state[3:] / 2 - MU / np.linalg.norm(state[:3]))
