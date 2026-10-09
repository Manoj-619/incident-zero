from __future__ import annotations
import hashlib
import json
from typing import Any


def new_evidence_id(
    tool_name: str, arguments: dict[str, Any], output: dict[str, Any]
) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": arguments, "out": output},
        sort_keys=True,
        default=str,
    )
    return "ev-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def new_experiment_id(code: str) -> tuple[str, str]:
    digest = hashlib.sha256(code.encode()).hexdigest()[:16]
    return "exp-" + digest, digest


def validate_citations(
    ids: list[str], allowed: set[str], *, require: bool = False
) -> None:
    if (require and not ids) or any(e not in allowed for e in ids):
        raise ValueError("Unsupported or missing evidence citations")
