# Numerical model and verification

All internal vectors use an Earth-centered inertial frame with **km, s, km/s**. Maneuver inputs/outputs are **m/s**. No reference epoch, Earth rotation, catalog identifiers, or geodetic ground track is claimed. Scenario object names are fictional.

## Dynamics and uncertainty

The state is $x=[r,v]$. With $\mu=398600.4418\;\mathrm{km^3/s^2}$,

$$\dot r=v,\qquad \dot v=-\mu r/\|r\|^3.$$

DOP853 integrates the state and the 6×6 state-transition matrix together:

$$\dot\Phi=A(x)\Phi,\quad A=\begin{bmatrix}0&I\\ \mu(3rr^T/\|r\|^5-I/\|r\|^3)&0\end{bmatrix},\quad P(t)=\Phi P_0\Phi^T.$$

The initial states are constructed by integrating backward from a prescribed synthetic encounter. Initial diagonal state covariance is supplied explicitly; it is not inferred from TLEs. Object errors are assumed independent, so relative position covariance is the sum of propagated position covariances. There is no process noise.

A maneuver is a deterministic inertial velocity impulse selected in the nominal radial/tangential/normal frame. State covariance is continuous through that fixed impulse. Burn-direction dependence on uncertain states and execution uncertainty are excluded.

## Closest approach

Distance is sampled across the full 2,400-second horizon. Every bracketed local minimum is refined using bounded scalar minimization; endpoints and the burn instant are also checked. This is a finite numerical search. Extremely narrow or unsampled minima in arbitrary imported trajectories are not ruled out. The shipped scenarios contain smooth, high-speed interior crossings.

## Encounter-plane probability

For the short encounter approximation, a 2×3 orthonormal basis $B$ perpendicular to relative velocity projects relative mean and covariance:

$$m=B(r_s-r_p),\qquad C=B(P_{p,rr}+P_{s,rr})B^T.$$

For combined hard-body radius $R$, collision probability is the Gaussian mass inside a disk:

$$P_c=\int_{\|u\|\le R}\frac{\exp[-\tfrac12(u-m)^TC^{-1}(u-m)]}{2\pi\sqrt{\det C}}\,du.$$

The planner uses tensor Gauss–Legendre quadrature in polar coordinates. Invalid covariance is rejected. Relative speeds below 0.1 km/s are rejected because the short encounter approximation is not intended for slow/co-orbital encounters. Velocity uncertainty is omitted from the instantaneous encounter integral, although it contributes to propagated position covariance.

Stress tests multiply **standard deviation** by 0.5, 1, and 2: covariance is multiplied by the square of that factor. The acceptance gate uses the worst stressed probability over **every listed object**. Risk is not monotonic in covariance size; increased uncertainty can either raise or dilute the disk probability.

## Maneuver search

The default policy searches both signs on each RTN axis at 20%, 45%, and 70% of the earliest risky TCA. Magnitudes are 1/16, 1/8, 1/4, 1/2, and 1 times the declared delta-v budget. The first feasible magnitude bracket in each direction is refined six times. The cheapest feasible evaluated direction is selected, with a 3% margin capped at the budget.

This is a reproducible discrete search with local direction refinement. It is **not** an unrestricted continuous optimizer, a global minimum proof, or an operational maneuver prescription. A failed search blocks approval; it does not prove that no feasible maneuver exists.

## Independent checks

The verifier independently integrates nominal states with fixed-step RK4 (2 seconds), splits the step exactly at the burn, and estimates TCA from a cubic interpolant. It compares each miss distance against the planner (<0.5 m error) and the primary path against DOP853 (<0.5 m error).

Collision probability is recomputed with a different algorithm: covariance eigenbasis rotation, a conditional normal CDF in one direction, and adaptive Cartesian quadrature in the other. It must agree to max(10⁻¹⁰ absolute, 10⁻⁴ relative), and every stressed result must meet the requested threshold. Both methods share the same physical and Gaussian covariance assumptions. Probability is checked using the planner's encounter mean/covariance; the RK4 check independently verifies nominal trajectory geometry, not covariance propagation.

A seeded 100,000-sample Monte Carlo diagnostic reports a Wilson 95% interval. Zero observed collisions does **not** establish zero risk. Monte Carlo is not the approval gate; it lacks resolution for many rare-event probabilities.

## Evidence and tests

Tests cover closed-form isotropic Gaussian mass, rotational invariance, independent quadrature agreement, circular orbit return, energy/angular momentum conservation, STM finite differences, covariance positivity, impulse continuity, independent trajectory agreement, no-burn cases, inadequate budgets, and rejected corrupted miss-distance evidence. API tests cover capability ownership, approval idempotency, provider gating, event streaming, retention/recovery, and quota.

## References

- [NASA CARA: publicly available analysis software](https://www.nasa.gov/cara/publicly-available-cara-software/)
- [NASA Spaceflight Safety Handbook, encounter-plane discussion](https://www.nasa.gov/wp-content/uploads/2020/03/spaceflight_safety_handbook_for_operators_v1.5_aug201.pdf)
- [SciPy solve_ivp / DOP853](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html)
- [ESA automated collision avoidance](https://www.esa.int/Space_Safety/Space_Debris/CREAM_avoiding_collisions_in_space_through_automation)

This repository contains an original educational implementation. It does not embed NASA CARA source or claim NASA/ESA certification.
