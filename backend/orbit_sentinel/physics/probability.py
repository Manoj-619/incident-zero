"""Short-encounter 2D Gaussian collision probability, quadrature, and uncertainty diagnostics."""

from functools import lru_cache

import numpy as np
from scipy.integrate import quad
from scipy.special import ndtr

from .dynamics import Array


def encounter_plane(relative_velocity: Array) -> Array:
    speed = np.linalg.norm(relative_velocity)
    if speed < 0.1:
        raise ValueError("Slow encounters are outside the short-encounter model.")
    direction = relative_velocity / speed
    reference = np.eye(3)[np.argmin(np.abs(direction))]
    first = np.cross(direction, reference)
    first /= np.linalg.norm(first)
    return np.stack((first, np.cross(direction, first)))


def validate_covariance(covariance: Array):
    if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
        raise ValueError("Expected a finite 2x2 covariance.")
    if not np.allclose(covariance, covariance.T, atol=1e-12, rtol=1e-10):
        raise ValueError("Covariance must be symmetric.")
    if np.min(np.linalg.eigvalsh(covariance)) <= 0:
        raise ValueError("Covariance must be positive definite.")


@lru_cache(maxsize=4)
def polar_nodes(order: int):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    return nodes, weights


def disk_probability(mean: Array, covariance: Array, radius: float, order: int = 32) -> float:
    """Integrate N(mean, covariance) over the combined hard-body disk in kilometers."""
    validate_covariance(covariance)
    if radius <= 0 or not np.isfinite(radius):
        raise ValueError("Hard-body radius must be positive and finite.")
    nodes, weights = polar_nodes(order)
    radial = (nodes + 1) * radius / 2
    theta = (nodes + 1) * np.pi
    points = np.stack(
        (radial[:, None] * np.cos(theta)[None, :], radial[:, None] * np.sin(theta)[None, :]),
        axis=-1,
    )
    displacement = points - mean
    exponent = np.einsum("...i,ij,...j->...", displacement, np.linalg.inv(covariance), displacement)
    density = np.exp(-0.5 * exponent) / (2 * np.pi * np.sqrt(np.linalg.det(covariance)))
    integral = np.sum(density * radial[:, None] * weights[:, None] * weights[None, :])
    return float(np.clip(integral * radius / 2 * np.pi, 0, 1))


def independent_disk_probability(mean: Array, covariance: Array, radius: float) -> float:
    """Independent Cartesian conditional-normal quadrature; no polar grid reused."""
    validate_covariance(covariance)
    # Rotate into covariance eigenbasis; a disk is rotationally invariant.
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    rotated = eigenvectors.T @ mean
    sx, sy = np.sqrt(eigenvalues)

    def integrand(x: float) -> float:
        bound = np.sqrt(max(0, radius**2 - x**2))
        density_x = np.exp(-0.5 * ((x - rotated[0]) / sx) ** 2) / (np.sqrt(2 * np.pi) * sx)
        y_mass = ndtr((bound - rotated[1]) / sy) - ndtr((-bound - rotated[1]) / sy)
        return float(density_x * max(0, y_mass))

    probability, _error = quad(integrand, -radius, radius, epsabs=1e-12, epsrel=1e-7, limit=150)
    return float(np.clip(probability, 0, 1))


def monte_carlo(
    mean: Array, covariance: Array, radius: float, seed: int, count: int = 100_000
) -> dict:
    samples = np.random.default_rng(seed).multivariate_normal(mean, covariance, count)
    hits = int(np.count_nonzero(np.linalg.norm(samples, axis=1) <= radius))
    estimate = hits / count
    z = 1.959963984540054
    denominator = 1 + z * z / count
    center = (estimate + z * z / (2 * count)) / denominator
    half = z * np.sqrt(estimate * (1 - estimate) / count + z * z / (4 * count**2)) / denominator
    return {
        "samples": count,
        "hits": hits,
        "estimate": estimate,
        "wilson_95": [max(0, center - half), min(1, center + half)],
        "note": "Zero hits is not zero risk. Monte Carlo is diagnostic, not the acceptance gate.",
    }
