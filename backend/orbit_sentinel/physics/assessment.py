"""Screen each catalog object over the full horizon and stress position covariance."""

from dataclasses import dataclass

import numpy as np

from ..scenarios import Scenario
from .dynamics import Trajectory, closest_approach
from .probability import disk_probability, encounter_plane


@dataclass
class Encounter:
    object_id: str
    time_s: float
    miss_km: float
    relative_speed_kms: float
    mean_km: np.ndarray
    covariance_km2: np.ndarray
    radius_km: float
    probability: float
    stresses: list[dict]

    def export(self) -> dict:
        eigenvalues, eigenvectors = np.linalg.eigh(self.covariance_km2)
        return {
            "object_id": self.object_id,
            "tca_s": self.time_s,
            "miss_distance_m": self.miss_km * 1000,
            "relative_speed_kms": self.relative_speed_kms,
            "probability": self.probability,
            "mean_plane_m": (self.mean_km * 1000).tolist(),
            "covariance_plane_m2": (self.covariance_km2 * 1e6).tolist(),
            "ellipse_3sigma_m": (3 * np.sqrt(eigenvalues) * 1000).tolist(),
            "ellipse_rotation_rad": float(np.arctan2(eigenvectors[1, 0], eigenvectors[0, 0])),
            "hard_body_radius_m": self.radius_km * 1000,
            "stress_tests": self.stresses,
            "worst_stress_probability": max(s["probability"] for s in self.stresses),
        }


class AssessmentEngine:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.secondaries = {
            obj.id: Trajectory(obj.state, obj.covariance, scenario.horizon_s)
            for obj in scenario.debris
        }

    def assess(self, primary: Trajectory, stress_scales=(0.5, 1.0, 2.0)) -> list[Encounter]:
        encounters = []
        for obj in self.scenario.debris:
            secondary = self.secondaries[obj.id]
            time, miss = closest_approach(primary, secondary)
            relative = secondary.state(time) - primary.state(time)
            plane = encounter_plane(relative[3:])
            mean = plane @ relative[:3]
            covariance = (
                plane
                @ (primary.position_covariance(time) + secondary.position_covariance(time))
                @ plane.T
            )
            radius = self.scenario.primary.radius_km + obj.radius_km
            probability = disk_probability(mean, covariance, radius)
            stresses = [
                {
                    "sigma_scale": scale,
                    "probability": disk_probability(mean, covariance * scale**2, radius),
                }
                for scale in stress_scales
            ]
            encounters.append(
                Encounter(
                    obj.id,
                    time,
                    miss,
                    float(np.linalg.norm(relative[3:])),
                    mean,
                    covariance,
                    radius,
                    probability,
                    stresses,
                )
            )
        return sorted(encounters, key=lambda event: event.probability, reverse=True)
