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
    state = InvestigationState.model_validate(data)
    from app.evidence import validate_citations

    validate_citations(
        state.verdict.evidence_ids,
        {r.evidence_id for r in state.tool_calls},
        require=True,
    )
    validate_citations(
        state.verdict.experiment_ids, {e.experiment_id for e in state.experiments}
    )
    state.events.insert(
        0,
        {
            "phase": "replay",
            "message": "Illustrative scripted example trace; not a recorded live AI investigation.",
        },
    )
    if state.remediation:
        state.remediation.intervention_id = "shorten_lock_window"
    return state
