from __future__ import annotations

from typing import Any, Callable

from app.evidence import new_evidence_id
from app.models import ToolCallRecord
from app.scenarios import Scenario

ToolFn = Callable[[Scenario, dict[str, Any]], dict[str, Any]]


def _fetch_metrics(scenario: Scenario, _args: dict[str, Any]) -> dict[str, Any]:
    return {"metrics": scenario.tool_fixtures["fetch_metrics"]}


def _fetch_logs(scenario: Scenario, args: dict[str, Any]) -> dict[str, Any]:
    logs = scenario.tool_fixtures["fetch_logs"]
    limit = int(args.get("limit", 50))
    sample = logs["sample"][:limit]
    return {"logs": sample, "count": len(sample)}


def _fetch_traces(scenario: Scenario, _args: dict[str, Any]) -> dict[str, Any]:
    return {"traces": scenario.tool_fixtures["fetch_traces"]}


TOOL_REGISTRY: dict[str, ToolFn] = {
    "fetch_metrics": _fetch_metrics,
    "fetch_logs": _fetch_logs,
    "fetch_traces": _fetch_traces,
}

TOOL_SCHEMAS = [
    {
        "name": "fetch_metrics",
        "description": "Fetch time-series aggregates for checkout, Redis pool, and DB lock wait.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "fetch_logs",
        "description": "Fetch recent structured logs for checkout and dependencies.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max log lines"}},
            "required": [],
        },
    },
    {
        "name": "fetch_traces",
        "description": "Fetch trace analysis summary for the hot checkout path.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


def run_tool(
    scenario: Scenario,
    tool_name: str,
    arguments: dict[str, Any],
) -> ToolCallRecord:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")
    output = TOOL_REGISTRY[tool_name](scenario, arguments)
    eid = new_evidence_id(tool_name, arguments, output)
    return ToolCallRecord(
        tool_name=tool_name,
        arguments=arguments,
        output=output,
        evidence_id=eid,
    )
