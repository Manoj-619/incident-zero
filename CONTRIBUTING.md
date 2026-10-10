# Contributing

ORBIT SENTINEL welcomes collaboration on orbital dynamics, uncertainty estimation, evaluation, and mission visualization.

1. Open an issue describing the behavior or mathematical assumption you want to change.
2. Keep units explicit: km, s, km/s internally; m/s for maneuver inputs and outputs.
3. Add a meaningful oracle or independent check for a new numerical method. Avoid tests that merely repeat the implementation.
4. Run `make test` and `make build` before proposing changes.
5. Update `docs/NUMERICS.md` when changing physics, covariance assumptions, probability methods, tolerances, or acceptance rules.

High-value next steps:

- Add a validated J2 model and perturbation-sensitive covariance checks.
- Model maneuver execution uncertainty and correlated object state errors.
- Add CDM parsing with provenance and explicitly supplied covariance.
- Benchmark encounter probability against NASA CARA reference cases without claiming certification.
- Add rare-event importance sampling with uncertainty diagnostics.
- Expand candidate search and verify multi-encounter tradeoffs over longer horizons.
- Add UI interaction tests and real browser/WebGL visual validation.

The numerical safety gate and human approval boundary must remain authoritative. A provider narrative cannot replace evidence or authorize a command. Do not submit secrets, unlicensed datasets, or real spacecraft control integrations as demonstration fixtures.

No license grant is currently included. Ask the maintainer about reuse terms before redistributing or deploying derived copies; contributions should be discussed with the maintainer before submission.
