from __future__ import annotations

import json
from pathlib import Path

from app.models import InvestigationState

_REPLAY_MAP = {
    "checkout-p99-spike": "checkout_p99_replay.json",
}


def load_replay(scenario_id: str) -> InvestigationState:
    filename = _REPLAY_MAP.get(scenario_id)
    if not filename:
        raise KeyError(f"No replay for scenario: {scenario_id}")
    path = Path(__file__).parent / filename
    data = json.loads(path.read_text())
    return InvestigationState.model_validate(data)
