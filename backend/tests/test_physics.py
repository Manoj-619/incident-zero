import numpy as np
import pytest

from orbit_sentinel.physics.dynamics import (
    MU,
    Trajectory,
    closest_approach,
    rtn_frame,
    specific_energy,
)
from orbit_sentinel.physics.probability import (
    disk_probability,
    encounter_plane,
    independent_disk_probability,
    monte_carlo,
)
from orbit_sentinel.physics.verification import independent_path
from orbit_sentinel.scenarios import make_scenario


def test_circular_orbit_period_energy_and_angular_momentum():
    initial = np.array([7000.0, 0, 0, 0, np.sqrt(MU / 7000), 0])
    period = 2 * np.pi * np.sqrt(7000**3 / MU)
    path = Trajectory(initial, np.eye(6) * 1e-8, period)
    np.testing.assert_allclose(path.state(period), initial, atol=2e-6)
    assert abs(specific_energy(path.state(period)) - specific_energy(initial)) < 1e-9
    np.testing.assert_allclose(
        np.cross(path.state(period)[:3], path.state(period)[3:]),
        np.cross(initial[:3], initial[3:]),
        atol=1e-6,
    )


def test_variational_solution_matches_finite_difference():
    scenario = make_scenario("crossing")
    initial = scenario.primary.state
    path = Trajectory(initial, scenario.primary.covariance, 2400)
    phi = path.augmented(900)[6:].reshape(6, 6)
    for axis in range(6):
        step = 1e-4 if axis < 3 else 1e-7
        offset = np.eye(6)[axis] * step
        plus = Trajectory(initial + offset, scenario.primary.covariance, 2400)
        minus = Trajectory(initial - offset, scenario.primary.covariance, 2400)
        numerical = (plus.state(900) - minus.state(900)) / (2 * step)
        np.testing.assert_allclose(phi[:, axis], numerical, rtol=3e-5, atol=1e-5)
    assert np.min(np.linalg.eigvalsh(path.position_covariance(900))) > 0


def test_impulse_is_position_continuous_and_has_declared_velocity_cost():
    scenario = make_scenario("crossing")
    path = Trajectory(
        scenario.primary.state,
        scenario.primary.covariance,
        2400,
        burn_time=300,
        dv_rtn_ms=np.array([0.0, 0.25, 0.0]),
    )
    before = path.pre.sol(300)
    after = path.state(300)
    np.testing.assert_allclose(before[:3], after[:3], atol=1e-10)
    assert np.linalg.norm(after[3:] - before[3:6]) * 1000 == pytest.approx(0.25, abs=1e-8)
    np.testing.assert_allclose(
        rtn_frame(before[:6]).T @ rtn_frame(before[:6]), np.eye(3), atol=1e-12
    )
    np.testing.assert_allclose(path.augmented(300)[6:], before[6:], atol=1e-10)


def test_constructed_close_approach_and_independent_integrator():
    scenario = make_scenario("crossing")
    primary = Trajectory(scenario.primary.state, scenario.primary.covariance, 2400)
    obj = scenario.debris[0]
    secondary = Trajectory(obj.state, obj.covariance, 2400)
    tca, distance = closest_approach(primary, secondary)
    assert tca == pytest.approx(900, abs=0.01)
    assert distance * 1000 == pytest.approx(35.47, abs=0.05)
    times, positions = independent_path(scenario.primary.state, 2400)
    error_m = (
        np.max(np.linalg.norm(positions - np.array([primary.state(t)[:3] for t in times]), axis=1))
        * 1000
    )
    assert error_m < 0.001


@pytest.mark.parametrize("sigma,radius", [(0.05, 0.012), (0.12, 0.01), (0.03, 0.015)])
def test_centered_isotropic_gaussian_matches_closed_form(sigma, radius):
    covariance = np.eye(2) * sigma**2
    exact = 1 - np.exp(-(radius**2) / (2 * sigma**2))
    assert disk_probability(np.zeros(2), covariance, radius) == pytest.approx(exact, rel=1e-10)
    assert independent_disk_probability(np.zeros(2), covariance, radius) == pytest.approx(
        exact, rel=1e-8
    )


def test_probability_rotation_invariance_and_independent_quadrature():
    angle = 0.73
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    covariance = np.array([[0.0064, 0.001], [0.001, 0.0025]])
    mean = np.array([0.055, 0.018])
    expected = disk_probability(mean, covariance, 0.012)
    actual = disk_probability(rotation @ mean, rotation @ covariance @ rotation.T, 0.012)
    assert actual == pytest.approx(expected, rel=1e-10)
    assert independent_disk_probability(mean, covariance, 0.012) == pytest.approx(
        expected, rel=1e-8
    )


@pytest.mark.parametrize(
    "covariance",
    [
        np.zeros((2, 2)),
        np.array([[1, 2], [2, 1]]),
        np.array([[1, 1], [0, 1]]),
        np.full((2, 2), np.nan),
    ],
)
def test_bad_covariance_is_rejected(covariance):
    with pytest.raises(ValueError):
        disk_probability(np.zeros(2), covariance, 0.01)


def test_encounter_plane_is_orthonormal_and_rejects_slow_approach():
    relative = np.array([1.0, 2.0, 3.0])
    plane = encounter_plane(relative)
    np.testing.assert_allclose(plane @ relative, np.zeros(2), atol=1e-12)
    np.testing.assert_allclose(plane @ plane.T, np.eye(2), atol=1e-12)
    with pytest.raises(ValueError):
        encounter_plane(np.zeros(3))


def test_monte_carlo_reproducibility_and_zero_hit_upper_bound():
    first = monte_carlo(np.zeros(2), np.eye(2) * 0.005, 0.012, 42)
    assert first == monte_carlo(np.zeros(2), np.eye(2) * 0.005, 0.012, 42)
    exact = disk_probability(np.zeros(2), np.eye(2) * 0.005, 0.012)
    assert first["wilson_95"][0] < exact < first["wilson_95"][1]
    rare = monte_carlo(np.array([10.0, 10.0]), np.eye(2) * 0.001, 0.012, 42)
    assert rare["hits"] == 0 and rare["wilson_95"][1] > 0
