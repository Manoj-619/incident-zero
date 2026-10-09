from __future__ import annotations

from app.evidence import new_experiment_id
from app.models import ExperimentResult
from app.sandbox.runner import run_deterministic_script
from app.scenarios import Scenario


def run_experimenter(
    scenario: Scenario,
    hypothesis: str,
) -> ExperimentResult:
    h = hypothesis.lower()
    if "redis" in h or "pool" in h:
        template = "pool_exhaustion_sim"
    else:
        template = "db_lock_sim"

    code_key = scenario.counterfactual_script_template
    if "redis" in h or "pool" in h:
        template = code_key if code_key in ("pool_exhaustion_sim",) else "pool_exhaustion_sim"

    from app.sandbox.runner import SCRIPT_MAP

    code = SCRIPT_MAP[template]()
    exp_id, code_hash = new_experiment_id(code)
    stdout, stderr, exit_code = run_deterministic_script(template)

    supports: bool | None = None
    for line in stdout.splitlines():
        if "supports_redis_pool_hypothesis=" in line:
            supports = line.strip().endswith("True")
        if "supports_db_lock_hypothesis=" in line:
            supports = line.strip().endswith("True")

    summary = "Counterfactual simulation completed via deterministic Python subprocess."
    if supports is False:
        summary = "Simulation does not support the current leading hypothesis."
    elif supports is True:
        summary = "Simulation supports the current leading hypothesis."

    return ExperimentResult(
        experiment_id=exp_id,
        hypothesis_tested=hypothesis,
        code_hash=code_hash,
        stdout=stdout.strip(),
        stderr=stderr.strip(),
        exit_code=exit_code,
        summary=summary,
        supports_hypothesis=supports,
    )
