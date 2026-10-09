from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any


def new_evidence_id(tool_name: str, arguments: dict[str, Any], output: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": arguments, "out": output},
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"ev-{digest}"


def new_experiment_id(code: str) -> tuple[str, str]:
    code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
    return f"exp-{uuid.uuid4().hex[:8]}", code_hash
