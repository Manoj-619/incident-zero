from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class Scenario(BaseModel):
    scenario_id: str
    title: str
    alert_text: str
    public_summary: str
    initial_hypothesis_hint: str
    ground_truth_internal_only: str
    tool_fixtures: dict
    counterfactual_script_template: str


_SCENARIOS: dict[str, Scenario] = {}


def _load() -> None:
    if _SCENARIOS:
        return
    root = Path(__file__).parent
    for path in root.glob("*.json"):
        data = json.loads(path.read_text())
        s = Scenario.model_validate(data)
        _SCENARIOS[s.scenario_id] = s


def get_scenario(scenario_id: str) -> Scenario:
    _load()
    if scenario_id not in _SCENARIOS:
        raise KeyError(f"Unknown scenario: {scenario_id}")
    return _SCENARIOS[scenario_id]


def list_scenarios() -> list[Scenario]:
    _load()
    return list(_SCENARIOS.values())
