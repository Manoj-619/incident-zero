from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

SANDBOX_DIR = Path(__file__).parent / "scripts"


def pool_exhaustion_sim_code() -> str:
    """Deterministic simulation: doubling Redis pool cannot explain observed checkout P99 if lock wait dominates."""
    return textwrap.dedent(
        """
        # Deterministic counterfactual: Redis pool vs DB lock wait
        metrics = {
            "checkout_p99_ms_observed": 2140,
            "redis_pool_wait_ms_p99": 4,
            "db_lock_wait_ms_p99": 1820,
        }
        # If we double pool, wait drops at most proportionally from current negligible base
        simulated_redis_wait = max(1, metrics["redis_pool_wait_ms_p99"] // 2)
        # Lock wait unchanged in this counterfactual
        simulated_checkout_p99 = (
            metrics["checkout_p99_ms_observed"]
            - metrics["redis_pool_wait_ms_p99"]
            + simulated_redis_wait
            + metrics["db_lock_wait_ms_p99"]
        )
        supports_pool_hypothesis = simulated_checkout_p99 < 800
        print("simulated_checkout_p99_ms=", simulated_checkout_p99)
        print("supports_redis_pool_hypothesis=", supports_pool_hypothesis)
        """
    ).strip()


def db_lock_sim_code() -> str:
    return textwrap.dedent(
        """
        # Counterfactual: stagger settlement batch reduces lock overlap
        lock_wait_p99_before = 1820
        lock_wait_p99_after = 420
        checkout_p99_after = 610
        print("lock_wait_p99_after=", lock_wait_p99_after)
        print("checkout_p99_after=", checkout_p99_after)
        print("supports_db_lock_hypothesis=", checkout_p99_after < 800)
        """
    ).strip()


SCRIPT_MAP = {
    "pool_exhaustion_sim": pool_exhaustion_sim_code,
    "db_lock_sim": db_lock_sim_code,
}


def run_deterministic_script(template: str, timeout_seconds: float = 5.0) -> tuple[str, str, int]:
    if template not in SCRIPT_MAP:
        return "", f"unknown script template: {template}", 1
    code = SCRIPT_MAP[template]()
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return proc.stdout, proc.stderr, proc.returncode
