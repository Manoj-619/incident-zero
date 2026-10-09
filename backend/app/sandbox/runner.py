"""Allowlisted pure Python simulations; no model-generated code execution."""

INTERVENTIONS = {"increase_pool", "shorten_lock_window"}


def simulate(intervention, metrics=None):
    if intervention not in INTERVENTIONS:
        raise ValueError("Unsupported intervention")
    m = metrics or {
        "checkout_p99_ms": 2140,
        "redis_pool_wait_ms_p99": 4,
        "db_lock_wait_ms_p99": 1820,
    }
    total, pool, lock = (
        float(m[k])
        for k in ("checkout_p99_ms", "redis_pool_wait_ms_p99", "db_lock_wait_ms_p99")
    )
    pool_after = pool / 2 if intervention == "increase_pool" else pool
    lock_after = lock * 0.25 if intervention == "shorten_lock_window" else lock
    return {
        "checkout_p99_before_ms": total,
        "checkout_p99_after_ms": max(0, total - pool - lock) + pool_after + lock_after,
        "pool_wait_after_ms": pool_after,
        "lock_wait_after_ms": lock_after,
    }


def pool_exhaustion_sim_code():
    return "additive-latency-v2: increase_pool; pool_wait *= 0.5"


def db_lock_sim_code():
    return "additive-latency-v2: shorten_lock_window; lock_wait *= 0.25"


SCRIPT_MAP = {
    "pool_exhaustion_sim": pool_exhaustion_sim_code,
    "db_lock_sim": db_lock_sim_code,
}


def run_deterministic_script(template, timeout_seconds=5):
    mapping = {
        "pool_exhaustion_sim": "increase_pool",
        "db_lock_sim": "shorten_lock_window",
    }
    if template not in mapping:
        return "", "unsupported template", 1
    values = simulate(mapping[template])
    label = "redis_pool" if template == "pool_exhaustion_sim" else "db_lock"
    return (
        "simulated_checkout_p99_ms="
        + str(values["checkout_p99_after_ms"])
        + "\nsupports_"
        + label
        + "_hypothesis="
        + str(values["checkout_p99_after_ms"] < 800),
        "",
        0,
    )
